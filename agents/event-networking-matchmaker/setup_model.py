"""Download public model weights once. This command never reads attendee data."""
import os
from pathlib import Path
import argparse

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir",default=str(Path(__file__).resolve().parent/"models"))
    parser.add_argument("--direct",action="store_true",help="Use bounded standard HTTPS downloads instead of the hub transport")
    args=parser.parse_args()
    os.environ["HF_HUB_DISABLE_TELEMETRY"]="1"
    os.environ["HF_HUB_DISABLE_XET"]="1"
    os.environ.pop("HF_HUB_OFFLINE",None)
    from fastembed import TextEmbedding
    import onnxruntime
    onnxruntime.disable_telemetry_events()
    from nlp import MODEL
    if args.direct:
        import httpx
        target=Path(args.cache_dir)/"minilm-local"
        target.mkdir(parents=True,exist_ok=True)
        for name in ("config.json","special_tokens_map.json","tokenizer.json","tokenizer_config.json","model.onnx"):
            output=target/name
            if output.exists():
                continue
            print(f"Downloading {name}...",flush=True)
            revision="d13954661f83248295ba75c1ed411eef3b7b936e"
            with httpx.stream("GET",f"https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/{revision}/{name}?download=true",follow_redirects=True,timeout=30) as response:
                response.raise_for_status()
                total=0
                temp=output.with_suffix(output.suffix+".partial")
                with temp.open("wb") as handle:
                    for chunk in response.iter_bytes(1024*1024):
                        total+=len(chunk)
                        if total>110*1024*1024:
                            raise ValueError("Unexpected model file size")
                        handle.write(chunk)
                        if name=="model.onnx":
                            print(f"Downloaded {total//(1024*1024)} MB",flush=True)
                temp.replace(output)
        model=TextEmbedding(model_name=MODEL,specific_model_path=str(target),local_files_only=True,threads=2)
        list(model.embed(["A public model setup check."]))
        print(f"BUILDBUDDY_MODEL_DIR={target.resolve()}")
        return
    model=TextEmbedding(model_name=MODEL,cache_dir=args.cache_dir,threads=2)
    list(model.embed(["A public model setup check."]))
    # Locate the downloaded model by its public ONNX file, without private APIs.
    paths=list(Path(args.cache_dir).rglob("model.onnx"))
    if len(paths)!=1:
        raise SystemExit("Set BUILDBUDDY_MODEL_DIR to the downloaded model directory containing tokenizer.json.")
    path=paths[0].parent
    if not (path/"tokenizer.json").exists():
        path=path.parent
    print("Model ready. Set this in .env and restart:")
    print(f"BUILDBUDDY_MODEL_DIR={path.resolve()}")

if __name__=="__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit("Model setup cancelled. The app still works in local lexical NLP mode.")
