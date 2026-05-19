import os
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error

# --- KONFIGURASI ---
NASA_DATASET_DIR = "../datasets/electrical/nasa/" # Taruh file CSV NASA di sini
MODEL_OUTPUT_PATH = "../models/weights/soh_xgb_model.json"

def preprocess_nasa_data(directory):
    """
    Fungsi ini mem-parsing dataset NASA. 
    Karena struktur asli NASA berbentuk .mat, asumsikan Anda sudah mengonversinya 
    menjadi CSV yang berisi siklus 'discharge' dengan format yang mudah dibaca.
    """
    print(f"[*] Mencari data CSV di: {directory}")
    if not os.path.exists(directory):
        print(f"[!] Direktori tidak ditemukan. Membuat folder kosong...")
        os.makedirs(directory)
        
        # --- MOCK DATA GENERATOR UNTUK TESTING HARI INI ---
        print("[*] Membuat MOCK DATASET untuk keperluan testing sementara...")
        np.random.seed(42)
        n_samples = 500
        
        # Simulasi fitur kelistrikan:
        # v_drop: seberapa banyak tegangan turun saat diberi beban (V)
        # internal_r: resistansi internal (Ohm)
        # temp_delta: kenaikan suhu (Celcius)
        v_drop = np.random.uniform(0.1, 1.2, n_samples)
        internal_r = np.random.uniform(0.05, 0.5, n_samples)
        temp_delta = np.random.uniform(0.5, 5.0, n_samples)
        
        # Rumus buatan untuk SoH (Hanya Mockup. Di dunia nyata, XGBoost yang mencari rumusnya)
        soh = 100 - (v_drop * 30) - (internal_r * 50) + np.random.normal(0, 2, n_samples)
        soh = np.clip(soh, 20, 100) # Pastikan rentang 20% - 100%
        
        df = pd.DataFrame({
            'v_drop': v_drop,
            'internal_r': internal_r,
            'temp_delta': temp_delta,
            'soh': soh
        })
        df.to_csv(os.path.join(directory, "mock_nasa_data.csv"), index=False)
        return df

    # Jika Anda sudah menaruh data NASA beneran:
    files = [f for f in os.listdir(directory) if f.endswith('.csv')]
    if not files:
        print("[!] Tidak ada file CSV ditemukan.")
        return None
        
    df_list = []
    for file in files:
        df = pd.read_csv(os.path.join(directory, file))
        # Logic ekstraksi fitur NASA sungguhan ditaruh di sini
        # (Misal: mencari nilai tegangan terendah dari array per baris)
        df_list.append(df)
        
    return pd.concat(df_list, ignore_index=True)

def train_model():
    print("=== RECELL-AI: XGBoost SOH Training ===")
    df = preprocess_nasa_data(NASA_DATASET_DIR)
    
    if df is None:
        print("[X] Training dibatalkan karena tidak ada data.")
        return

    # 1. Pisahkan Fitur (X) dan Target (y)
    X = df[['v_drop', 'internal_r', 'temp_delta']] # Ini fitur yang dibaca STM32
    y = df['soh'] # Target yang ingin diprediksi

    # 2. Split Data (80% Train, 20% Test)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # 3. Inisialisasi Model XGBoost
    model = xgb.XGBRegressor(
        objective='reg:squarederror',
        n_estimators=100,
        learning_rate=0.1,
        max_depth=5
    )

    # 4. Training
    print("[*] Memulai Training...")
    model.fit(X_train, y_train)

    # 5. Evaluasi Akurasi
    y_pred = model.predict(X_test)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    print(f"[*] Training Selesai! RMSE: {rmse:.2f}% (Rata-rata tebakan meleset {rmse:.2f} persen)")

    # 6. Simpan Model
    os.makedirs(os.path.dirname(MODEL_OUTPUT_PATH), exist_ok=True)
    model.save_model(MODEL_OUTPUT_PATH)
    print(f"[*] Model berhasil disimpan di: {MODEL_OUTPUT_PATH}")

if __name__ == "__main__":
    train_model()
