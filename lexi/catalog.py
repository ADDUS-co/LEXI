"""Read and validate the human-editable vocabulary files."""

import json
from pathlib import Path


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read {Path(path).name}: {error}") from error


def validate_catalog(collections, words):
    if not isinstance(collections, list) or not collections:
        raise ValueError("collections.json must contain a non-empty array.")
    if not isinstance(words, list) or not words:
        raise ValueError("words.json must contain a non-empty array.")
    collection_ids = set()
    for collection in collections:
        if not isinstance(collection, dict):
            raise ValueError("Each collection must be a JSON object.")
        for field in ("id", "name", "description", "icon"):
            if not isinstance(collection.get(field), str) or not collection[field].strip():
                raise ValueError(f"Collection is missing a non-empty {field}.")
        if collection["id"] in collection_ids:
            raise ValueError(f"Duplicate collection ID: {collection['id']}")
        collection_ids.add(collection["id"])
    word_ids = set()
    for word in words:
        if not isinstance(word, dict):
            raise ValueError("Each word must be a JSON object.")
        for field in ("id", "collectionId", "word", "partOfSpeech", "ipa",
                      "shortDefinition", "fullDefinition", "simpleExplanation"):
            if not isinstance(word.get(field), str) or not word[field].strip():
                raise ValueError(f"Word {word.get('id', '?')} is missing a non-empty {field}.")
        if word["id"] in word_ids:
            raise ValueError(f"Duplicate word ID: {word['id']}")
        word_ids.add(word["id"])
        if word["collectionId"] not in collection_ids:
            raise ValueError(f"Unknown collection for {word['id']}.")
        if (not isinstance(word.get("examples"), list) or not word["examples"]
                or any(not isinstance(item, str) or not item.strip() for item in word["examples"])):
            raise ValueError(f"Word {word['id']} needs at least one example sentence.")
        for field in ("synonyms", "relatedWords"):
            if not isinstance(word.get(field, []), list):
                raise ValueError(f"{field} must be an array for {word['id']}.")
            for item in word.get(field, []):
                if not isinstance(item, dict) or not isinstance(item.get("word"), str) or not item["word"].strip():
                    raise ValueError(f"Invalid {field} entry for {word['id']}.")
                if "definition" in item and not isinstance(item["definition"], str):
                    raise ValueError(f"Invalid {field} definition for {word['id']}.")
        for field in ("usageNote", "difficulty"):
            if field in word and not isinstance(word[field], str):
                raise ValueError(f"{field} must be text for {word['id']}.")
        if "source" in word:
            source = word["source"]
            if (not isinstance(source, dict) or not isinstance(source.get("label"), str)
                    or not isinstance(source.get("url"), str) or not source["url"].startswith("https://")):
                raise ValueError(f"Invalid reference for {word['id']}.")
    for collection_id in collection_ids:
        if not any(word["collectionId"] == collection_id for word in words):
            raise ValueError(f"Collection {collection_id} has no vocabulary yet.")


def load_catalog(root):
    collections = read_json(root / "data" / "collections.json")
    words = read_json(root / "data" / "words.json")
    validate_catalog(collections, words)
    site = read_json(root / "data" / "site.json")
    if not isinstance(site, dict) or any(not isinstance(site.get(field), str) for field in ("name", "tagline", "description")):
        raise ValueError("site.json needs name, tagline, and description text fields.")
    if not isinstance(site.get("contacts", []), list):
        raise ValueError("site.json contacts must be an array.")
    for contact in site.get("contacts", []):
        if not isinstance(contact, dict) or any(not isinstance(contact.get(field), str) for field in ("label", "text", "url", "icon")):
            raise ValueError("Each contact needs label, text, url, and icon fields.")
    return collections, words, site

