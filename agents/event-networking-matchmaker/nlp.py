"""Local language retrieval. No profile vectors or queries are saved to disk."""
from collections import Counter
import math
import os
from pathlib import Path
import re
import threading

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
STOP = set("a an and are as at be been by can could do for from get have help how i in into is it know like me my of on or our please someone start that the their them there these they this to want what who with would you your need looking find people person learn about interested interests building project".split())
ALIASES = {"js":"javascript", "ts":"typescript", "k8s":"kubernetes", "gcp":"google cloud",
           "ui design":"design", "apis":"api", "backend":"api", "back end":"api",
           "deploy":"deployment", "opensource":"open source"}
EXPANSIONS = {
    "open source": ["git", "documentation", "contribution", "contributor", "pull request"],
    "mobile app": ["flutter", "android", "mobile"],
    "deploy": ["deployment", "hosting", "docker"],
    "put my app online": ["deployment", "hosting"],
    "run ai offline": ["gemma", "local", "model"],
    "local ai": ["gemma", "local", "model"],
    "first pull request": ["git", "documentation", "open source", "contribution"],
    "first contribution": ["git", "documentation", "open source", "contribution"],
    "test an agent": ["evaluation", "testing"],
    "screen reader": ["accessibility"],
}

def normalize(text):
    return re.sub(r"\s+", " ", text.lower().replace("open-source", "open source")).strip()

def tags(text):
    return {ALIASES.get(t, t) for t in (normalize(x) for x in re.split(r"[,;\n]", text)) if t}

def tokens(text):
    result = []
    for word in re.findall(r"[a-z0-9+#]+", normalize(text)):
        if word in STOP:
            continue
        if len(word)>6 and word.endswith("ing"):
            word=word[:-3]
        elif len(word)>4 and word.endswith("s"):
            word=word[:-1]
        result.append(word)
    return result

def query_terms(query):
    expanded=[]
    for phrase, additions in EXPANSIONS.items():
        if phrase in normalize(query):
            expanded.extend(additions)
    return tokens(query),sorted(set(expanded))

def bm25(query, documents):
    docs=[tokens(d) for d in documents]
    if not docs:
        return []
    avg=max(1,sum(map(len,docs))/len(docs))
    df=Counter(t for doc in docs for t in set(doc))
    scores=[]
    for doc in docs:
        counts=Counter(doc)
        value=0.0
        for term in set(query):
            tf=counts[term]
            if tf:
                idf=math.log(1+(len(docs)-df[term]+0.5)/(df[term]+0.5))
                value+=idf*tf*2.2/(tf+1.2*(0.25+0.75*len(doc)/avg))
        scores.append(value)
    return scores

class LocalEncoder:
    """One local model; request-local vectors avoid stale/withdrawn profile indexes."""
    def __init__(self, model_dir=None):
        self.model=None
        self.lock=threading.Lock()
        self.error=None
        self.path=model_dir or os.getenv("BUILDBUDDY_MODEL_DIR")
        if self.path:
            try:
                os.environ["HF_HUB_OFFLINE"]="1"
                os.environ["HF_HUB_DISABLE_TELEMETRY"]="1"
                from fastembed import TextEmbedding
                import onnxruntime
                onnxruntime.disable_telemetry_events()
                self.model=TextEmbedding(model_name=MODEL,specific_model_path=str(Path(self.path).resolve()),local_files_only=True,threads=2)
            except Exception:
                self.error="Local semantic model could not be loaded. Using lexical NLP; check BUILDBUDDY_MODEL_DIR."

    @property
    def available(self):
        return self.model is not None

    def similarities(self, query, documents):
        if not self.model or not documents:
            return [0.0]*len(documents)
        try:
            with self.lock:
                if self.model is None:
                    return [0.0]*len(documents)
                vectors=list(self.model.embed([query,*documents],batch_size=64))
            import numpy as np
            q=vectors[0]
            return [float(np.dot(q,d)/max(float(np.linalg.norm(q)*np.linalg.norm(d)),1e-9)) for d in vectors[1:]]
        except Exception:
            self.model=None
            self.error="Local semantic inference failed. Using lexical NLP; restart after checking the model installation."
            return [0.0]*len(documents)
