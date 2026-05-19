from ultralytics import YOLO
import argparse
import os

def main(data_yaml, epochs, batch_size):
    print("=== RECELL-AI: YOLOv8 Training Pipeline ===")
    
    if not os.path.exists(data_yaml):
        print(f"[!] File {data_yaml} tidak ditemukan! Pastikan Anda sudah download dataset dari Roboflow.")
        return

    # 1. Load Pre-trained Nano model (Fastest for Jetson)
    model = YOLO('yolov8n.pt')

    # 2. Train the model
    print(f"[*] Memulai training {epochs} epochs, batch {batch_size}...")
    results = model.train(
        data=data_yaml,
        epochs=epochs,
        batch=batch_size,
        imgsz=640,
        device=0, # Gunakan GPU (0) jika di PC/Colab
        project='../models',
        name='recell_vision',
        exist_ok=True
    )

    # 3. Export to TensorRT (Bisa dilakukan nanti di Jetson)
    best_model_path = '../models/recell_vision/weights/best.pt'
    print(f"\n[*] Training selesai! Model terbaik disimpan di: {best_model_path}")
    print("[!] UNTUK JETSON: Jangan lupa jalankan perintah export ke TensorRT di terminal Jetson:")
    print(f"    yolo export model={best_model_path} format=engine half=True workspace=4")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=str, default='../datasets/vision/data.yaml', help='Path ke file data.yaml dari Roboflow')
    parser.add_argument('--epochs', type=int, default=100, help='Jumlah epoch training')
    parser.add_argument('--batch', type=int, default=16, help='Batch size')
    args = parser.parse_args()
    
    main(args.data, args.epochs, args.batch)
