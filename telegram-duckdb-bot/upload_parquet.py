#!/usr/bin/env python3
"""
upload_parquet.py - Prepara e faz upload dos arquivos Parquet para deploy.

Uso:
    # Criar arquivo tar.gz para upload manual
    python upload_parquet.py pack /caminho/para/parquet_export /data/parquet.tar.gz
    
    # Listar arquivos (para copiar via scp/rsync)
    python upload_parquet.py list /caminho/para/parquet_export
"""

import os, sys, tarfile, glob, hashlib

def cmd_pack(src_dir, out_file):
    src_dir = os.path.abspath(src_dir)
    parquet_files = sorted(glob.glob(os.path.join(src_dir, "*.parquet")))
    if not parquet_files:
        print("ERRO: Nenhum arquivo .parquet encontrado em", src_dir)
        sys.exit(1)
    
    print(f"Compactando {len(parquet_files)} arquivos de {src_dir} -> {out_file}")
    total_size = sum(os.path.getsize(f) for f in parquet_files)
    print(f"Tamanho total: {total_size / 1024**3:.2f} GB")
    
    with tarfile.open(out_file, "w:gz") as tar:
        for f in parquet_files:
            arcname = os.path.basename(f)
            tar.add(f, arcname=arcname)
            print(f"  + {arcname} ({os.path.getsize(f)/1024**2:.0f} MB)")
    
    out_size = os.path.getsize(out_file)
    print(f"\nArquivo criado: {out_file}")
    print(f"Tamanho compactado: {out_size / 1024**3:.2f} GB")
    print(f"Taxa de compressao: {out_size/total_size*100:.1f}%")
    
    # MD5 para verificação
    md5 = hashlib.md5()
    with open(out_file, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            md5.update(chunk)
    print(f"MD5: {md5.hexdigest()}")

def cmd_list(src_dir):
    src_dir = os.path.abspath(src_dir)
    files = sorted(glob.glob(os.path.join(src_dir, "*.parquet")))
    total = sum(os.path.getsize(f) for f in files)
    print(f"{len(files)} arquivos, {total/1024**3:.2f} GB total:")
    for f in files:
        sz = os.path.getsize(f)
        name = os.path.basename(f)
        print(f"  {name}: {sz/1024**2:.0f} MB")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    cmd = sys.argv[1]
    if cmd == "pack":
        if len(sys.argv) < 4:
            print("Uso: python upload_parquet.py pack <src_dir> <out_file>")
            sys.exit(1)
        cmd_pack(sys.argv[2], sys.argv[3])
    elif cmd == "list":
        if len(sys.argv) < 3:
            print("Uso: python upload_parquet.py list <src_dir>")
            sys.exit(1)
        cmd_list(sys.argv[2])
    else:
        print(f"Comando desconhecido: {cmd}")
        sys.exit(1)
