"""
Metadata extraction module for AI-generated images
Supports PNG, JPG, JPEG, WebP formats
"""
import json
import re
import html
import unicodedata
import subprocess
import os
from PIL import Image
from collections import namedtuple

# Metaadat struktúra
ImageMeta = namedtuple("ImageMeta", [
    "prompt",           # 0
    "neg_prompt",      
    "model",           
    "sampler",         
    "scheduler",       
    "steps",           
    "cfg_scale",       
    "seed",            
    "denoise",          # 8 - opcionális, ha kell
    "vae",            
    "loras"             # 10 - lista a több LoRA-ra
])

def empty_meta():
    """Visszaad egy alapértelmezett, üres ImageMeta namedtuple-t."""
    return ImageMeta(
        prompt="N/A",
        neg_prompt="N/A",
        model="-",
        sampler="-",
        scheduler="-",
        steps="-",
        cfg_scale="-",
        seed="-",
        denoise="-",
        vae="-",
        loras=[]
    )

def find_all_keys(d, key):
    """
    Rekurzívan megkeresi az összes adott kulcsot a JSON-ban.
    Minden előfordulás értékét listában adja vissza.
    """
    results = []
    if isinstance(d, dict):
        for k, v in d.items():
            if k == key:
                results.append(v)
            elif isinstance(v, (dict, list)):
                results.extend(find_all_keys(v, key))
    elif isinstance(d, list):
        for item in d:
            results.extend(find_all_keys(item, key))
    return results

def extract_loras_from_usercomment(raw_uc):
    """
    Kinyeri a LoRA-kat a JPG UserComment mezőből JSON formátumból.
    Visszaad egy listát: [(name, weight), ...]
    """
    loras = []
    if isinstance(raw_uc, str):
        raw_text = raw_uc
    else:
        try:
            raw_text = json.dumps(raw_uc, ensure_ascii=False)
        except Exception:
            raw_text = str(raw_uc)

    try:
        matches = re.findall(r'\{[^\}]*"type"\s*:\s*"lora"[^\}]*\}', raw_text)
        for m in matches:
            try:
                d = json.loads(m)
                if d.get("type") == "lora":
                    name = d.get("modelName", "Unknown")
                    weight = d.get("weight", 1.0)
                    loras.append((name, weight))
            except Exception:
                continue
    except Exception:
        pass

    return loras

def extract_loras(obj):
    """Kinyeri a LoRA-kat PNG formátumokból."""
    results = []

    def recursive_find_lora(o):
        if isinstance(o, dict):
            if "lora_name" in o:
                name = o["lora_name"]
                weight = o.get("strength_model", o.get("weight", 1.0))
                results.append((name, weight))
            for v in o.values():
                recursive_find_lora(v)
        elif isinstance(o, list):
            for item in o:
                recursive_find_lora(item)

    recursive_find_lora(obj)

    # Text formátum keresése
    if isinstance(obj, str):
        text = obj
    elif isinstance(obj, dict):
        text = obj.get("text", "")
    else:
        text = str(obj)

    lora_pattern = r"<lora:([^:>]+):([\d.]+)>"
    matches = re.findall(lora_pattern, text)
    for name, weight in matches:
        try:
            w = float(weight)
        except ValueError:
            w = 1.0
        results.append((name.strip(), w))

    # Duplikátumok kiszűrése
    unique = {}
    for name, weight in results:
        unique[name] = weight
    final_list = [(n, unique[n]) for n in unique]

    return final_list

def decode_surrogate_pair(txt):
    if not txt:
        return "-"
    try:
        import codecs
        return codecs.decode(txt, 'unicode_escape')
    except Exception:
        return txt

def extract_from_usercomment(raw_uc):
    """JPG UserComment feldolgozása"""
    pos = neg = step = sampler = cfg = seed = denoise = scheduler = vae = loras = ckpt = "no"
    try:
        if raw_uc.strip().startswith("{"):
            data = json.loads(raw_uc)

            if "extraMetadata" in data:
                extra = json.loads(data["extraMetadata"])
                pos = extra.get("prompt", "-")
                neg = extra.get("negativePrompt", "-")
                sampler = extra.get("sampler", "-")
                step = str(extra.get("steps", "-"))
                cfg = str(extra.get("cfgScale", "-"))
                ckpt = extra.get("modelName", "-")
                
                # Checkpoint név tisztítása
                if ckpt != "-":
                    ckpt = os.path.basename(ckpt)
                
                seed = str(extra.get("seed", "-"))
                scheduler = str(extra.get("scheduler", "-"))
                denoise = str(extra.get("denoise", "-"))
                vae = str(extra.get("vae", "-"))
                loras = extract_loras_from_usercomment(data)
                
                if not seed or seed == "-":
                    seeds = find_all_keys(data, "seed")
                    seed = seeds[0] if seeds else "-"
                if not scheduler or scheduler == "-":
                    schedulers = find_all_keys(data, "scheduler")
                    scheduler = schedulers[0] if schedulers else "-"
                if not loras or loras == "no":
                    lora_names = find_all_keys(data, "lora_name")
                    lora_strengths = find_all_keys(data, "strength_model")
                    loras = list(zip(lora_names, lora_strengths))

            # ComfyUI specifikus
            for k, v in data.items():
                if isinstance(v, dict) and v.get("class_type") == "smZ CLIPTextEncode":
                    if v.get("_meta", {}).get("title") == "Positive":
                        pos = v["inputs"].get("text", pos)
                    elif v.get("_meta", {}).get("title") == "Negative":
                        neg = v["inputs"].get("text", neg)

                if isinstance(v, dict) and v.get("class_type") == "CheckpointLoaderSimple":
                    ckpt = v["inputs"].get("ckpt_name", ckpt)
                    # Checkpoint név tisztítása
                    if ckpt != "no" and ckpt != "-":
                        ckpt = os.path.basename(ckpt)

                if isinstance(v, dict) and v.get("class_type") == "FaceDetailer":
                    step = str(v["inputs"].get("steps", step))
                    cfg = str(v["inputs"].get("cfg", cfg))
                    sampler = v["inputs"].get("sampler_name", sampler)
                    seed = str(v["inputs"].get("seed", seed))
                    scheduler = str(v["inputs"].get("scheduler", scheduler))
                    denoise = str(v["inputs"].get("denoise", denoise))
                    vae = str(v["inputs"].get("vae", seed))
                    loras = extract_loras_from_usercomment(raw_uc)

        else:
            # Szöveges formátum
            m = re.split(r"Steps:|steps:", raw_uc, 1)
            if len(m) > 1:
                pos = m[0].strip().rstrip(",.")
            else:
                pos = raw_uc.strip()

            neg_m = re.search(r"Negative prompt:\s*(.*)", raw_uc, re.IGNORECASE)
            if neg_m:
                neg = neg_m.group(1).strip()

            step_m = re.search(r"Steps:\s*(\d+)", raw_uc)
            if step_m:
                step = step_m.group(1)

            sampler_m = re.search(r"Sampler:\s*([^\n,]+)", raw_uc)
            if sampler_m:
                sampler = sampler_m.group(1).strip()

            cfg_m = re.search(r"CFG scale:\s*([\d.]+)", raw_uc, re.IGNORECASE)
            if cfg_m:
                cfg = cfg_m.group(1)

            seed_m = re.search(r"Seed:\s*(\d+)", raw_uc)
            if seed_m:
                seed = seed_m.group(1)

            scheduler_m = re.search(r"Scheduler:\s*([^\n,]+)", raw_uc)
            if scheduler_m:
                scheduler = scheduler_m.group(1).strip()

            denoise_m = re.search(r"Denoise:\s*([\d.]+)", raw_uc)
            if denoise_m:
                denoise = denoise_m.group(1)

            vae_m = re.search(r"Vae:\s*([^\n,]+)", raw_uc)
            if vae_m:
                vae = vae_m.group(1).strip()

            loras = extract_loras_from_usercomment(raw_uc)

            model_m = re.search(r'"modelName":"([^"]+)"', raw_uc)
            if model_m:
                ckpt = model_m.group(1)
                # Checkpoint név tisztítása
                ckpt = os.path.basename(ckpt)

            pos = decode_surrogate_pair(pos)
            neg = decode_surrogate_pair(neg)
            ckpt = decode_surrogate_pair(ckpt)

    except Exception as e:
        print(f"[ERROR] extract_from_usercomment: {e}")

    return ImageMeta(
        prompt=pos,
        neg_prompt=neg,
        model=ckpt,
        sampler=sampler,
        scheduler=scheduler,
        steps=step,
        cfg_scale=cfg,
        seed=seed,
        denoise=denoise,
        vae=vae,
        loras=loras
    )

def extract_prompts_jpg(image_path):
    """JPG metaadat kinyerése exiftool használatával"""
    try:
        result = subprocess.run(
            ["exiftool", "-j", "-UserComment", image_path],
            capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if data and "UserComment" in data[0]:
                raw_uc = data[0]["UserComment"]
                parsed = extract_from_usercomment(raw_uc)
                if parsed:
                    return parsed

        return empty_meta()

    except Exception as e:
        print(f"[ERROR] extract_prompts_jpg: {e}")
        return empty_meta()

def extract_prompts_png(image_path):
    """PNG metaadat kinyerése"""
    try:
        img = Image.open(image_path)
        metadata = img.info

        raw_prompt = metadata.get("prompt") or metadata.get("parameters") or metadata.get("Description") or metadata.get("comment") or None
        if not raw_prompt:
            return empty_meta()

        # JSON parse próbálkozás
        try:
            prompt_json = json.loads(raw_prompt)
        except Exception:
            # Nem JSON, sima szöveg
            text_all = str(raw_prompt)
            text_all = " ".join(text_all.split())
            meta = empty_meta()
            return meta._replace(prompt=text_all)

        # Text mezők gyűjtése
        texts = []
        def collect_texts(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == "text" and isinstance(v, str):
                        texts.append(v)
                    else:
                        collect_texts(v)
            elif isinstance(obj, list):
                for item in obj:
                    collect_texts(item)
        collect_texts(prompt_json)

        pos = texts[0] if len(texts) > 0 else "N/A"
        neg = texts[1] if len(texts) > 1 else "N/A"

        # Kulcsok keresése
        def find_key(obj, target):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == target:
                        return v
                    res = find_key(v, target)
                    if res is not None:
                        return res
            elif isinstance(obj, list):
                for item in obj:
                    res = find_key(item, target)
                    if res is not None:
                        return res
            return None

        ckpt = find_key(prompt_json, "ckpt_name") or "-"
        if ckpt == "-":
            ckpt = find_key(prompt_json, "unet_name") or "-"
        
        # Checkpoint név tisztítása - levágni az útvonalat
        if ckpt != "-":
            ckpt = os.path.basename(ckpt)
        
        sampler = find_key(prompt_json, "sampler_name") or "-"
        scheduler = find_key(prompt_json, "scheduler") or "-"
        step = find_key(prompt_json, "steps") or "-"
        cfg = find_key(prompt_json, "cfg") or "-"
        seed = find_key(prompt_json, "seed") or "-"
        denoise = find_key(prompt_json, "denoise") or "-"
        vae = find_key(prompt_json, "vae") or "-"
        loras = extract_loras(prompt_json)

        return ImageMeta(
            prompt=pos,
            neg_prompt=neg,
            model=ckpt,
            sampler=sampler,
            scheduler=scheduler,
            steps=step,
            cfg_scale=cfg,
            seed=seed,
            denoise=denoise,
            vae=vae,
            loras=loras
        )

    except Exception as e:
        print(f"[ERROR] extract_prompts_png: {e}")
        return empty_meta()

def extract_prompts(fname):
    """Központi metaadat kinyerő - formátum alapján hívja a megfelelő függvényt"""
    ext = os.path.splitext(fname)[1].lower()

    if ext == ".png":
        img = Image.open(fname)
        metadata = img.info

        if "prompt" in metadata:
            return extract_prompts_png(fname)
        elif "parameters" in metadata:
            # A1111 formátum
            raw = metadata["parameters"]

            pos = re.search(r'^(.*?)\s*,?\s*Negative prompt:', raw, re.DOTALL)
            neg = re.search(r'Negative prompt:\s*(.*?)\s*,?\s*Steps:', raw)
            sampler = re.search(r'Sampler:\s*(.*?)(?=,|$)', raw)
            cfg = re.search(r'CFG scale:\s*(.*?)(?=,|$)', raw)
            step = re.search(r'Steps:\s*(.*?)(?=,|$)', raw)
            seed = re.search(r'Seed:\s*(.*?)(?=,|$)', raw)
            ckpt = re.search(r'Model:\s*(.*?)(?=,|$)', raw)
            scheduler = re.search(r'Scheduler:\s*(.*?)(?=,|$)', raw)
            denoise = re.search(r'Denoising strength:\s*(.*?)(?=,|$)', raw)
            vae = re.search(r'VAE:\s*(.*?)(?=,|$)', raw)
            loras = extract_loras(raw)

            pos = pos.group(1).replace("\n", " ") if pos else "N/A"
            neg = neg.group(1).replace("\n", " ") if neg else "N/A"
            ckpt = ckpt.group(1) if ckpt else "-"
            
            # Checkpoint név tisztítása
            if ckpt != "-":
                ckpt = os.path.basename(ckpt)
            
            sampler = sampler.group(1) if sampler else "-"
            step = step.group(1) if step else "-"
            scheduler = scheduler.group(1) if scheduler else "-"
            cfg = cfg.group(1) if cfg else "-"
            seed = seed.group(1) if seed else "-"
            denoise = denoise.group(1) if denoise else "-"
            vae = vae.group(1) if vae else "-"

            return ImageMeta(
                prompt=pos,
                neg_prompt=neg,
                model=ckpt,
                sampler=sampler,
                scheduler=scheduler,
                steps=step,
                cfg_scale=cfg,
                seed=seed,
                denoise=denoise,
                vae=vae,
                loras=loras
            )
        else:
            return empty_meta()

    elif ext in (".jpg", ".jpeg"):
        return extract_prompts_jpg(fname)
    else:
        return empty_meta()

