"""This module loads HTML from files, cleans up, splits, and ingests into Weaviate."""

import logging
import os
import re
import weaviate

from chatbot_api.parsers import custom_site_extractor
from bs4 import BeautifulSoup, SoupStrainer
from chatbot_api.constants import WEAVIATE_DOCS_INDEX_NAME
from langchain.document_loaders import RecursiveUrlLoader, SitemapLoader, CSVLoader
from langchain.indexes import SQLRecordManager, index
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.utils.html import PREFIXES_TO_IGNORE_REGEX, SUFFIXES_TO_IGNORE_REGEX
from langchain_community.vectorstores import Weaviate
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_embeddings_model() -> Embeddings:
    """Create and return an OpenAI embeddings model.

    Returns:
        Embeddings: The created embeddings model.
    """
    return OpenAIEmbeddings(model="text-embedding-3-small", chunk_size=200)


def metadata_extractor(meta: dict, soup: BeautifulSoup) -> dict:
    """Extract metadata from the given BeautifulSoup object.

    Args:
        meta (dict): The metadata to extract.
        soup (BeautifulSoup): The BeautifulSoup object to extract metadata from.

    Returns:
        dict: The extracted metadata.
    """
    title = soup.find("title")
    description = soup.find("meta", attrs={"name": "description"})
    html = soup.find("html")
    return {
        "source": meta["loc"],
        "title": title.get_text() if title else "",
        "description": description.get("content", "") if description else "",
        "language": html.get("lang", "") if html else "",
        **meta,
    }


def load_custom_site():
    """Load the custom site using a SitemapLoader.

    Returns:
        list: The loaded documents from the custom site.
    """
    return SitemapLoader(
        os.environ.get("LOAD_CUSTOM_SITE_URL"),
        filter_urls=[os.environ.get("FILTER_LOAD_CUSTOM_SITE_URL")],
        parsing_function=custom_site_extractor,
        default_parser="lxml",
        bs_kwargs={
            "parse_only": SoupStrainer(
                name=("article", "title", "html", "lang", "content", "description")
            ),
        },
        meta_function=metadata_extractor,
    ).load()


def load_custom_blog():
    """Load the custom blog using a RecursiveUrlLoader.

    Returns:
        list: The loaded documents from the custom blog.
    """
    return RecursiveUrlLoader(
        url=os.environ.get("LOAD_CUSTOM_BLOG_URL"),
        max_depth=8,
        extractor=simple_extractor,
        prevent_outside=True,
        use_async=True,
        timeout=600,
        # Drop trailing / to avoid duplicate pages.
        link_regex=(
            f"href=[\"']{PREFIXES_TO_IGNORE_REGEX}((?:{SUFFIXES_TO_IGNORE_REGEX}.)*?)"
            r"(?:[\#'\"]|\/[\#'\"])"
        ),
        check_response_status=True,
    ).load()


def simple_extractor(html: str) -> str:
    """Extract text from the given HTML string.

    Args:
        html (str): The HTML string to extract text from.

    Returns:
        str: The extracted text.
    """
    soup = BeautifulSoup(html, "lxml")
    return re.sub(r"\n\n+", "\n\n", soup.text).strip()


def load_custom_stock():
    """Load the custom stock using a CSVLoader.

    Returns:
        list: The loaded documents from the custom stock.
    """
    return CSVLoader(
        file_path="./csv/stock.csv",
        csv_args={
            "delimiter": ",",
            "fieldnames": [
                "stock_id",
                "km",
                "price",
                "make",
                "model",
                "year",
                "version",
                "bluetooth",
                "largo",
                "ancho",
                "altura",
                "car_play",
            ],
        },
    ).load()


def ingest_docs():
    """Ingest documents into Weaviate.

    This function loads documents from the custom site, custom stock, and custom blog, transforms them, and ingests them into Weaviate.
    """
    WEAVIATE_URL = os.environ["WEAVIATE_URL"]
    WEAVIATE_API_KEY = os.environ["WEAVIATE_API_KEY"]
    RECORD_MANAGER_DB_URL = os.environ["RECORD_MANAGER_DB_URL"]

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=4000, chunk_overlap=200)
    embedding = get_embeddings_model()

    client = weaviate.Client(
        url=WEAVIATE_URL,
        auth_client_secret=weaviate.AuthApiKey(api_key=WEAVIATE_API_KEY),
    )
    vectorstore = Weaviate(
        client=client,
        index_name=WEAVIATE_DOCS_INDEX_NAME,
        text_key="text",
        embedding=embedding,
        by_text=False,
        attributes=["source", "title"],
    )

    record_manager = SQLRecordManager(
        f"weaviate/{WEAVIATE_DOCS_INDEX_NAME}", db_url=RECORD_MANAGER_DB_URL
    )
    record_manager.create_schema()

    docs_from_custom = load_custom_site()
    logger.info(f"Loaded {len(docs_from_custom)} docs from custom")
    docs_from_custom_stock = load_custom_stock()
    logger.info(f"Loaded {len(docs_from_custom_stock)} docs from custom stock")
    docs_from_custom_blog = load_custom_blog()
    logger.info(f"Loaded {len(docs_from_custom_blog)} docs from custom blog")

    docs_transformed = text_splitter.split_documents(
        docs_from_custom + docs_from_custom_stock + docs_from_custom_blog
    )
    docs_transformed = [doc for doc in docs_transformed if len(doc.page_content) > 10]

    # We try to return 'source' and 'title' metadata when querying vector store and
    # Weaviate will error at query time if one of the attributes is missing from a
    # retrieved document.
    for doc in docs_transformed:
        if "source" not in doc.metadata:
            doc.metadata["source"] = ""
        if "title" not in doc.metadata:
            doc.metadata["title"] = ""

    indexing_stats = index(
        docs_transformed,
        record_manager,
        vectorstore,
        cleanup="full",
        source_id_key="source",
        force_update=(os.environ.get("FORCE_UPDATE") or "false").lower() == "true",
    )

    logger.info(f"Indexing stats: {indexing_stats}")
    num_vecs = client.query.aggregate(WEAVIATE_DOCS_INDEX_NAME).with_meta_count().do()
    logger.info(
        f"LangChain now has this many vectors: {num_vecs}",
    )


if __name__ == "__main__":
    """Main execution point of the application.

    This block is executed when the module is run directly, not when it is imported.
    It starts the ingestion of documents into Weaviate.
    """
    ingest_docs()
