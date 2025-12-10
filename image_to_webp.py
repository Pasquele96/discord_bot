#!/usr/bin/env python3
"""
Image to WebP Converter
Converte immagini JPEG, JPG e PNG in WebP con compressione ottimizzata.
Obiettivo: ridurre da ~1MB a <50KB mantenendo la massima qualità possibile.
"""

import os
import sys
import argparse
from pathlib import Path
from PIL import Image

# Formati supportati
SUPPORTED_FORMATS = {'.jpeg', '.jpg', '.png'}
TARGET_SIZE_KB = 50
MAX_QUALITY = 95
MIN_QUALITY = 10


def get_file_size_kb(file_path: str) -> float:
    """Restituisce la dimensione del file in KB."""
    return os.path.getsize(file_path) / 1024


def convert_image_to_webp(
    input_path: str,
    output_path: str = None,
    target_size_kb: int = TARGET_SIZE_KB,
    max_quality: int = MAX_QUALITY,
    min_quality: int = MIN_QUALITY
) -> dict:
    """
    Converte un'immagine in WebP cercando di raggiungere il target di dimensione.

    Strategia:
    1. Inizia con qualità alta
    2. Riduce progressivamente la qualità fino a raggiungere il target
    3. Usa compressione WebP lossy ottimizzata

    Args:
        input_path: Percorso dell'immagine di input
        output_path: Percorso di output (opzionale, default: stesso nome con .webp)
        target_size_kb: Dimensione target in KB
        max_quality: Qualità massima (0-100)
        min_quality: Qualità minima (0-100)

    Returns:
        dict con informazioni sulla conversione
    """
    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"File non trovato: {input_path}")

    if input_path.suffix.lower() not in SUPPORTED_FORMATS:
        raise ValueError(f"Formato non supportato: {input_path.suffix}. Formati supportati: {SUPPORTED_FORMATS}")

    # Determina il percorso di output
    if output_path is None:
        output_path = input_path.with_suffix('.webp')
    else:
        output_path = Path(output_path)

    # Apri l'immagine
    with Image.open(input_path) as img:
        # Converti in RGB se necessario (per immagini con trasparenza)
        if img.mode in ('RGBA', 'P'):
            # Mantieni la trasparenza per PNG con alpha
            if img.mode == 'P':
                img = img.convert('RGBA')
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        original_size_kb = get_file_size_kb(input_path)
        original_dimensions = img.size

        # Strategia di compressione adattiva
        best_quality = max_quality
        best_size = float('inf')

        # Binary search per trovare la qualità ottimale
        low_q = min_quality
        high_q = max_quality

        while low_q <= high_q:
            mid_q = (low_q + high_q) // 2

            # Salva temporaneamente per verificare la dimensione
            temp_path = output_path.with_suffix('.tmp.webp')

            save_kwargs = {
                'format': 'WEBP',
                'quality': mid_q,
                'method': 6,  # Metodo di compressione più lento ma migliore
            }

            # Aggiungi lossless solo per qualità molto alte se l'immagine è piccola
            if mid_q >= 95 and original_size_kb < 100:
                save_kwargs['lossless'] = True

            img.save(temp_path, **save_kwargs)
            current_size = get_file_size_kb(temp_path)

            if current_size <= target_size_kb:
                # Siamo sotto il target, proviamo qualità più alta
                best_quality = mid_q
                best_size = current_size
                low_q = mid_q + 1
            else:
                # Siamo sopra il target, riduciamo la qualità
                high_q = mid_q - 1

            # Rimuovi file temporaneo
            if temp_path.exists():
                temp_path.unlink()

        # Se non siamo riusciti a stare sotto il target, usa la qualità minima
        if best_size > target_size_kb:
            best_quality = min_quality

        # Salvataggio finale con la qualità ottimale
        save_kwargs = {
            'format': 'WEBP',
            'quality': best_quality,
            'method': 6,
        }

        img.save(output_path, **save_kwargs)
        final_size_kb = get_file_size_kb(output_path)

        # Calcola la riduzione percentuale
        reduction_percent = ((original_size_kb - final_size_kb) / original_size_kb) * 100 if original_size_kb > 0 else 0

        return {
            'input_path': str(input_path),
            'output_path': str(output_path),
            'original_size_kb': round(original_size_kb, 2),
            'final_size_kb': round(final_size_kb, 2),
            'quality_used': best_quality,
            'reduction_percent': round(reduction_percent, 1),
            'dimensions': original_dimensions,
            'target_reached': final_size_kb <= target_size_kb
        }


def convert_directory(
    input_dir: str,
    output_dir: str = None,
    target_size_kb: int = TARGET_SIZE_KB,
    recursive: bool = False
) -> list:
    """
    Converte tutte le immagini supportate in una directory.

    Args:
        input_dir: Directory di input
        output_dir: Directory di output (opzionale, default: stessa directory)
        target_size_kb: Dimensione target in KB
        recursive: Se True, cerca anche nelle sottodirectory

    Returns:
        Lista di dict con risultati delle conversioni
    """
    input_dir = Path(input_dir)

    if not input_dir.is_dir():
        raise NotADirectoryError(f"Non è una directory: {input_dir}")

    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    results = []

    # Trova tutti i file immagine
    pattern = '**/*' if recursive else '*'
    for file_path in input_dir.glob(pattern):
        if file_path.suffix.lower() in SUPPORTED_FORMATS:
            try:
                if output_dir:
                    # Mantieni la struttura delle sottodirectory
                    relative_path = file_path.relative_to(input_dir)
                    out_path = output_dir / relative_path.with_suffix('.webp')
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                else:
                    out_path = None

                result = convert_image_to_webp(
                    str(file_path),
                    str(out_path) if out_path else None,
                    target_size_kb
                )
                results.append(result)

                status = "✓" if result['target_reached'] else "⚠"
                print(f"{status} {file_path.name}: {result['original_size_kb']}KB → {result['final_size_kb']}KB ({result['reduction_percent']}% riduzione, qualità: {result['quality_used']})")

            except Exception as e:
                print(f"✗ Errore con {file_path.name}: {e}")
                results.append({
                    'input_path': str(file_path),
                    'error': str(e)
                })

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Converte immagini JPEG, JPG e PNG in WebP con compressione ottimizzata.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  python image_to_webp.py immagine.jpg
  python image_to_webp.py immagine.png -o output.webp
  python image_to_webp.py ./cartella_immagini/
  python image_to_webp.py ./input/ -d ./output/ -r
  python image_to_webp.py immagine.jpg -t 30  # Target 30KB
        """
    )

    parser.add_argument(
        'input',
        help='File immagine o directory da convertire'
    )

    parser.add_argument(
        '-o', '--output',
        help='Percorso di output per singolo file'
    )

    parser.add_argument(
        '-d', '--output-dir',
        help='Directory di output per conversione batch'
    )

    parser.add_argument(
        '-t', '--target-size',
        type=int,
        default=TARGET_SIZE_KB,
        help=f'Dimensione target in KB (default: {TARGET_SIZE_KB})'
    )

    parser.add_argument(
        '-q', '--max-quality',
        type=int,
        default=MAX_QUALITY,
        help=f'Qualità massima 0-100 (default: {MAX_QUALITY})'
    )

    parser.add_argument(
        '--min-quality',
        type=int,
        default=MIN_QUALITY,
        help=f'Qualità minima 0-100 (default: {MIN_QUALITY})'
    )

    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        help='Cerca ricorsivamente nelle sottodirectory'
    )

    args = parser.parse_args()

    input_path = Path(args.input)

    print(f"\n{'='*60}")
    print("   Image to WebP Converter")
    print(f"   Target: <{args.target_size}KB | Qualità max: {args.max_quality}")
    print(f"{'='*60}\n")

    if input_path.is_file():
        # Conversione singolo file
        try:
            result = convert_image_to_webp(
                str(input_path),
                args.output,
                args.target_size,
                args.max_quality,
                args.min_quality
            )

            print(f"File originale:  {result['input_path']}")
            print(f"File convertito: {result['output_path']}")
            print(f"Dimensioni:      {result['dimensions'][0]}x{result['dimensions'][1]}")
            print(f"Dimensione:      {result['original_size_kb']}KB → {result['final_size_kb']}KB")
            print(f"Riduzione:       {result['reduction_percent']}%")
            print(f"Qualità usata:   {result['quality_used']}")

            if result['target_reached']:
                print(f"\n✓ Target raggiunto! File sotto i {args.target_size}KB")
            else:
                print(f"\n⚠ Target non raggiunto. File ancora sopra i {args.target_size}KB")
                print("  Prova ad aumentare la compressione con --min-quality più basso")

        except Exception as e:
            print(f"✗ Errore: {e}")
            sys.exit(1)

    elif input_path.is_dir():
        # Conversione directory
        results = convert_directory(
            str(input_path),
            args.output_dir,
            args.target_size,
            args.recursive
        )

        # Statistiche finali
        successful = [r for r in results if 'error' not in r]
        failed = [r for r in results if 'error' in r]
        target_reached = [r for r in successful if r.get('target_reached', False)]

        print(f"\n{'='*60}")
        print("   Riepilogo")
        print(f"{'='*60}")
        print(f"File processati:     {len(results)}")
        print(f"Conversioni riuscite: {len(successful)}")
        print(f"Target raggiunto:    {len(target_reached)}/{len(successful)}")
        print(f"Errori:              {len(failed)}")

        if successful:
            total_original = sum(r['original_size_kb'] for r in successful)
            total_final = sum(r['final_size_kb'] for r in successful)
            total_reduction = ((total_original - total_final) / total_original) * 100 if total_original > 0 else 0
            print(f"\nSpazio risparmiato:  {total_original:.1f}KB → {total_final:.1f}KB ({total_reduction:.1f}%)")
    else:
        print(f"✗ Percorso non valido: {input_path}")
        sys.exit(1)

    print()


if __name__ == '__main__':
    main()
