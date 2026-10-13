from urllib.parse import urlsplit, urlunsplit

import requests


def ollama_api_url(endpoint, resource):
    parsed = urlsplit((endpoint or "http://localhost:11434").strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("Enter the Ollama server URL, such as http://localhost:11434.")
    path = parsed.path.rstrip("/")
    for suffix in ("/v1/chat/completions", "/api/chat", "/api/tags", "/v1", "/api"):
        if path.endswith(suffix):
            path = path[:-len(suffix)]
            break
    return urlunsplit((parsed.scheme, parsed.netloc, f"{path}/api/{resource}", "", ""))


def installed_ollama_models(endpoint):
    with requests.get(ollama_api_url(endpoint, "tags"), timeout=(5, 10)) as response:
        response.raise_for_status()
        data = response.json()
    models = data.get("models", [])
    names = []
    for model in models:
        name = model.get("name") or model.get("model")
        if isinstance(name, str) and name.strip() and name not in names:
            names.append(name)
    return names

