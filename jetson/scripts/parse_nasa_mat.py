import scipy.io
import pandas as pd
import numpy as np
import os
import argparse

def parse_mat_to_csv(mat_folder, output_csv):
    """
    Parses NASA Battery Dataset .mat files and extracts discharge curve features.
    
    The NASA dataset typically contains a structure like:
    battery['cycle'][0]['type'] == 'discharge'
    Then we extract voltage_measured, current_measured, temperature_measured.
    """
    print(f"[*] Scanning {mat_folder} for .mat files...")
    mat_files = [f for f in os.listdir(mat_folder) if f.endswith('.mat')]
    
    if not mat_files:
        print(f"[!] No .mat files found in {mat_folder}.")
        return

    all_features = []

    for file in mat_files:
        file_path = os.path.join(mat_folder, file)
        print(f"[*] Processing {file}...")
        
        try:
            mat = scipy.io.loadmat(file_path)
            # The exact key depends on the file name (e.g. B0005)
            batt_key = [k for k in mat.keys() if not k.startswith('__')][0]
            cycles = mat[batt_key]['cycle'][0,0][0]
            
            for cycle in cycles:
                if cycle['type'][0] == 'discharge':
                    data = cycle['data'][0,0]
                    
                    voltages = data['Voltage_measured'][0]
                    currents = data['Current_measured'][0]
                    temps = data['Temperature_measured'][0]
                    capacity = data['Capacity'][0][0] if 'Capacity' in data.dtype.names else None
                    
                    if capacity is None or len(voltages) < 10:
                        continue
                        
                    # Feature Extraction
                    v_initial = voltages[0]
                    v_drop_max = v_initial - np.min(voltages)
                    
                    # Estimate internal resistance during the initial load drop
                    # Assuming a constant current of approx 2A was applied
                    i_max = np.abs(np.min(currents))
                    internal_r = v_drop_max / i_max if i_max > 0 else 0
                    
                    temp_delta = np.max(temps) - temps[0]
                    
                    # Convert capacity (Ah) to SOH % (Assuming 2.0Ah is 100%)
                    soh = (capacity / 2.0) * 100
                    soh = np.clip(soh, 0, 100)
                    
                    all_features.append({
                        'v_drop': v_drop_max,
                        'internal_r': internal_r,
                        'temp_delta': temp_delta,
                        'soh': soh
                    })
                    
        except Exception as e:
            print(f"[!] Error processing {file}: {e}")

    df = pd.DataFrame(all_features)
    df.to_csv(output_csv, index=False)
    print(f"[*] Successfully extracted {len(df)} discharge cycles.")
    print(f"[*] Saved to {output_csv}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NASA .mat to CSV Parser for RECELL-AI")
    parser.add_argument('--input', type=str, default='../datasets/electrical/nasa/raw', help='Folder containing .mat files')
    parser.add_argument('--output', type=str, default='../datasets/electrical/nasa/parsed_nasa_data.csv', help='Output CSV file path')
    args = parser.parse_args()
    
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    if not os.path.exists(args.input):
        os.makedirs(args.input)
        print(f"[!] Please place NASA .mat files inside {args.input} before running.")
    else:
        parse_mat_to_csv(args.input, args.output)
