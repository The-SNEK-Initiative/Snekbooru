import json
import asyncio
import random

import requests
from PyQt5.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot, QThread
from PyQt5.QtGui import QPixmap

from snekbooru.api.booru import danbooru_posts
from snekbooru.common.constants import DEFAULT_AI_MODEL, USER_AGENT
from snekbooru.core.config import SETTINGS


class WorkerSignals(QObject):
    """Defines the signals available from a running worker thread."""
    finished = pyqtSignal(object, str)
    progress = pyqtSignal(int, int, str)

class AIWorkerSignals(QObject):
    """Defines signals for the AI streaming worker."""
    finished = pyqtSignal(str)
    chunk = pyqtSignal(str)
    error = pyqtSignal(str)

class ApiWorker(QRunnable):
    """Generic worker for running an API function in the background."""
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            # Pass both positional and keyword arguments to the target function
            # This is more flexible and robust.
            data = self.fn(*self.args, **self.kwargs) 
            self.signals.finished.emit(data, "")
        except Exception as e:
            self.signals.finished.emit(None, str(e))

class AsyncApiWorker(QRunnable):
    """Generic worker for running an async API function in the background."""
    def __init__(self, coro, *args, **kwargs):
        super().__init__()
        self.coro = coro
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            # asyncio.run() creates a new event loop, which is suitable for use in a thread.
            # This allows running async code from a synchronous QRunnable.
            data = asyncio.run(self.coro(*self.args, **self.kwargs))
            self.signals.finished.emit(data, "")
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            self.signals.finished.emit(None, str(e))

class AIStreamWorker(QRunnable):
    """Worker for streaming AI responses."""
    def __init__(self, messages, temperature):
        super().__init__()
        self.messages = messages
        self.temperature = temperature
        self.signals = AIWorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            # First check if the preset has a provider setting
            active_preset_index = SETTINGS.get("ai_active_preset_index", 0)
            presets = SETTINGS.get("ai_presets", [])
            
            if 0 <= active_preset_index < len(presets):
                preset = presets[active_preset_index]
                ai_provider = preset.get("provider", SETTINGS.get("ai_provider", "OpenRouter"))
            else:
                ai_provider = SETTINGS.get("ai_provider", "OpenRouter")
            
            if ai_provider == "Google Gemini (Experimental)":
                self._run_gemini()
            else:
                self._run_openrouter()
                
        except Exception as e: 
            self.signals.error.emit(str(e))

    def _run_openrouter(self):
        """Stream responses from OpenRouter API."""
        headers = {
            "Authorization": f"Bearer {SETTINGS.get('ai_api_key')}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/atroubledsnake/Snekbooru",
            "X-Title": "Snekbooru"
        }
        
        active_preset_index = SETTINGS.get("ai_active_preset_index", 0)
        active_preset = SETTINGS["ai_presets"][active_preset_index]
        model = active_preset.get("model", DEFAULT_AI_MODEL)

        payload = {"model": model, "messages": self.messages, "temperature": self.temperature, "stream": True}
        response = requests.post(SETTINGS.get('ai_endpoint', 'https://openrouter.ai/api/v1/chat/completions'), headers=headers, json=payload, timeout=120, stream=True)
        response.raise_for_status()
        
        full_response = ""
        for chunk in response.iter_lines():
            if chunk:
                line = chunk.decode('utf-8')
                if line.startswith('data: '):
                    content = line[6:]
                    if content.strip() == '[DONE]': break
                    try:
                        data = json.loads(content)
                        delta = data.get('choices', [{}])[0].get('delta', {})
                        if 'content' in delta and delta['content'] is not None:
                            content_chunk = delta['content']; full_response += content_chunk; self.signals.chunk.emit(content_chunk)
                    except (json.JSONDecodeError, KeyError, IndexError): continue
        self.signals.finished.emit(full_response)

    def _run_gemini(self):
        """Stream responses from Google Gemini API."""
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError(
                "Google Generative AI library not installed. "
                "Install it with: pip install google-generativeai"
            )
        
        api_key = SETTINGS.get("gemini_api_key", "")
        if not api_key:
            raise ValueError("Gemini API key not configured. Please add it in Settings > APIs.")
        
        genai.configure(api_key=api_key)
        
        active_preset_index = SETTINGS.get("ai_active_preset_index", 0)
        active_preset = SETTINGS["ai_presets"][active_preset_index]
        model_name = active_preset.get("model", "gemini-2.5-pro")
        
        # Get the system prompt from the preset
        system_prompt = active_preset.get("persona", "")
        
        # Create model with system prompt
        gemini_model = genai.GenerativeModel(
            model_name,
            system_instruction=system_prompt
        )
        
        # Convert OpenRouter format messages to Gemini format
        gemini_messages = []
        for msg in self.messages:
            role = "user" if msg["role"] == "user" else "model"
            gemini_messages.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })
        
        full_response = ""
        
        # Use streaming with Gemini - send full conversation
        response = gemini_model.generate_content(
            gemini_messages,
            generation_config=genai.types.GenerationConfig(temperature=self.temperature),
            stream=True
        )
        
        try:
            for chunk in response:
                if chunk and hasattr(chunk, 'text') and chunk.text:
                    full_response += chunk.text
                    self.signals.chunk.emit(chunk.text)
        except Exception as e:
            # Handle cases where response is empty or finish_reason indicates early stop
            if full_response:
                self.signals.finished.emit(full_response)
            else:
                raise ValueError("Gemini API returned an empty response. Try again or check your API key.")
        
        self.signals.finished.emit(full_response)

class ImageWorkerSignals(QObject):
    finished = pyqtSignal(QPixmap, dict)

class ImageWorker(QRunnable):
    """Worker for fetching an image."""
    def __init__(self, url, post):
        super().__init__()
        self.url, self.post = url, post
        self.signals = ImageWorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            from snekbooru.common.helpers import load_pixmap_from_data
            r = requests.get(self.url, headers={"User-Agent": USER_AGENT}, timeout=30)
            r.raise_for_status()
            pix = load_pixmap_from_data(r.content)
            self.signals.finished.emit(pix, self.post)
        except Exception as e:
            print(f"ImageWorker failed for {self.url}: {e}")
            self.signals.finished.emit(QPixmap(), self.post)

class DataFetcher(QThread):
    finished = pyqtSignal(bytes, dict, str)

    def __init__(self, url, post):
        super().__init__()
        self.url = url
        self.post = post

    def run(self):
        try:
            r = requests.get(self.url, headers={"User-Agent": USER_AGENT}, timeout=30)
            r.raise_for_status()
            self.finished.emit(r.content, self.post, "")
        except Exception as e:
            self.finished.emit(b"", self.post, str(e))

class RecommendationFetcher(QRunnable):
    """
    Worker that fetches recommendations by searching for top tags individually,
    retrying on failure, and collecting random posts from each successful search.
    """
    def __init__(self, top_tags, blacklisted_tags, posts_per_tag=3):
        super().__init__()
        self.top_tags = top_tags
        self.blacklisted_tags = blacklisted_tags
        self.posts_per_tag = posts_per_tag
        self.signals = WorkerSignals() # finished(object, str), progress(int, int, str)

    @pyqtSlot()
    def run(self):
        recommended_posts = []
        seen_ids = set()
        max_retries_per_tag = 5
        total_tags = len(self.top_tags)

        # Pre-calculate content filter tags to apply client-side, avoiding Danbooru's tag limit.
        content_filter_tags = []
        if SETTINGS.get("allow_loli_shota") != "true":
            content_filter_tags.extend(["loli", "shota"])
        if SETTINGS.get("allow_bestiality") != "true":
            content_filter_tags.append("bestiality")
        if SETTINGS.get("allow_guro") != "true":
            content_filter_tags.append("guro")
        
        try:
            for i, tag in enumerate(self.top_tags):
                self.signals.progress.emit(i, total_tags, f"Searching for tag: {tag}...")

                retries = 0
                found_for_tag = False
                while not found_for_tag and retries < max_retries_per_tag:
                    try:
                        page = random.randint(0, 50)
                        search_tag = tag
                        if not SETTINGS.get("allow_explicit", False):
                            search_tag += " rating:safe"

                        for blacklisted_tag in self.blacklisted_tags:
                            if blacklisted_tag:
                                search_tag += f" -{blacklisted_tag}"

                        posts, _ = danbooru_posts(search_tag, limit=50, page=page)

                        if posts:
                            random.shuffle(posts)
                            added_count = 0
                            for post in posts:
                                # Client-side filtering for content tags
                                post_tags = set(post.get('tag_string', '').split())
                                if any(filter_tag in post_tags for filter_tag in content_filter_tags):
                                    continue

                                post_id = post.get('id')
                                if post_id and post_id not in seen_ids:
                                    recommended_posts.append(post)
                                    seen_ids.add(post_id)
                                    added_count += 1
                                    
                                    if added_count >= self.posts_per_tag:
                                        break
                            if added_count > 0:
                                found_for_tag = True
                    except Exception as e:
                        print(f"Error fetching for tag '{tag}' on retry {retries}: {e}")
                    retries += 1
                    if not found_for_tag:
                        QThread.msleep(200)
                if not found_for_tag: print(f"Failed to find posts for tag '{tag}' after {max_retries_per_tag} retries.")
            random.shuffle(recommended_posts)
            self.signals.finished.emit((recommended_posts, 0), "")
        except Exception as e: self.signals.finished.emit(None, str(e))