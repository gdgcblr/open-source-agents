from typing import List, Dict, Any

class IngestionAgent:
    """
    Ingestion & Diarization Agent: Cleans, merges, and attributes incoming
    transcript chunks from Google Meet and Microsoft Teams content scripts.
    """
    
    def process_transcript(self, raw_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicates and merges consecutive chunks spoken by the same participant.
        """
        if not raw_chunks:
            return []
            
        merged: List[Dict[str, Any]] = []
        for chunk in raw_chunks:
            text = (chunk.get("text") or "").strip()
            speaker = (chunk.get("speaker") or "Speaker").strip()
            timestamp = chunk.get("timestamp")
            
            if not text:
                continue
                
            # If same speaker as previous chunk, merge if close in time
            if merged and merged[-1]["speaker"] == speaker:
                prev_text = merged[-1]["text"]
                if not prev_text.endswith((".", "!", "?")):
                    merged[-1]["text"] = f"{prev_text} {text}"
                else:
                    merged[-1]["text"] = f"{prev_text} {text}"
            else:
                merged.append({
                    "speaker": speaker,
                    "text": text,
                    "timestamp": timestamp
                })
                
        return merged
        
    def format_for_llm(self, chunks: List[Dict[str, Any]]) -> str:
        """
        Formats transcript lines for LLM consumption.
        """
        lines = []
        for c in chunks:
            lines.append(f"{c['speaker']}: {c['text']}")
        return "\n".join(lines)

