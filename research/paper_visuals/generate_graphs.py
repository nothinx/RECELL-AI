import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Set style for academic/poster graphs
plt.style.use('seaborn-v0_8-whitegrid')
sns.set_context("paper", font_scale=1.5)

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def generate_mock_data():
    """Generates synthetic data representing a batch of graded batteries."""
    np.random.seed(42)
    n = 200
    
    # Simulate electrical features
    v_drop = np.random.uniform(0.1, 0.8, n)
    internal_r = np.random.uniform(0.05, 0.3, n)
    
    # Calculate simulated SOH (higher drop/resistance = lower SOH)
    soh = 100 - (v_drop * 20) - (internal_r * 100) + np.random.normal(0, 3, n)
    soh = np.clip(soh, 20, 100)
    
    # Simulate Vision Scores
    vision_score = np.random.uniform(0.3, 1.0, n)
    
    # Determine Grades based on our algorithm logic
    grades = []
    for s, v in zip(soh, vision_score):
        if v < 0.4 or s < 60:
            grades.append("Grade R (Reject)")
        elif v > 0.8 and s > 80:
            grades.append("Grade A")
        else:
            grades.append("Grade B")
            
    return pd.DataFrame({
        'Battery_ID': [f'BAT_{i:03d}' for i in range(n)],
        'Voltage_Drop': v_drop,
        'Internal_Resistance': internal_r,
        'SOH': soh,
        'Vision_Score': vision_score,
        'Final_Grade': grades
    })

def plot_grade_distribution(df):
    """1. Bar Chart: Distribusi hasil grading (Cocok untuk menunjukkan throughput)"""
    plt.figure(figsize=(8, 6))
    ax = sns.countplot(x='Final_Grade', data=df, palette=['#2ecc71', '#ffc107', '#e74c3c'], 
                       order=["Grade A", "Grade B", "Grade R (Reject)"])
    plt.title('Distribution of Sorted Batteries', fontweight='bold')
    plt.xlabel('Battery Grade')
    plt.ylabel('Count')
    
    # Add counts on top of bars
    for p in ax.patches:
        ax.annotate(f'{int(p.get_height())}', (p.get_x() + p.get_width() / 2., p.get_height()),
                    ha='center', va='bottom', fontsize=12, color='black', xytext=(0, 5),
                    textcoords='offset points')
                    
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, '01_grade_distribution.png'), dpi=300)
    plt.close()

def plot_fusion_scatter(df):
    """2. Scatter Plot: Vision Score vs SOH (Menunjukkan mengapa Fusion AI penting)"""
    plt.figure(figsize=(10, 7))
    sns.scatterplot(x='SOH', y='Vision_Score', hue='Final_Grade', data=df, 
                    palette={'Grade A': '#2ecc71', 'Grade B': '#ffc107', 'Grade R (Reject)': '#e74c3c'},
                    s=100, alpha=0.8, edgecolor='black')
    
    # Add decision boundaries (dashed lines)
    plt.axvline(x=60, color='red', linestyle='--', alpha=0.5, label='SOH Reject Threshold')
    plt.axvline(x=80, color='green', linestyle='--', alpha=0.5, label='SOH A-Grade Threshold')
    plt.axhline(y=0.4, color='red', linestyle=':', alpha=0.5, label='Vision Reject Threshold')
    
    plt.title('AI Fusion Decision Mapping: Vision Score vs Electrical SOH', fontweight='bold')
    plt.xlabel('Electrical State of Health (SOH) %')
    plt.ylabel('Vision AI Score (Physical Integrity)')
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, '02_ai_fusion_scatter.png'), dpi=300, bbox_inches='tight')
    plt.close()

def plot_discharge_curve_simulation():
    """3. Line Chart: Simulasi Kurva Discharge Constant Current (Visualisasi kerja STM32)"""
    plt.figure(figsize=(10, 6))
    time_ms = np.linspace(0, 2000, 100) # 2 seconds
    
    # Healthy battery (Grade A) - minimal voltage drop
    volt_a = 4.1 - (time_ms/2000)*0.1 - 0.05*(1-np.exp(-time_ms/100))
    # Degraded battery (Grade R) - severe voltage drop
    volt_r = 4.0 - (time_ms/2000)*0.5 - 0.3*(1-np.exp(-time_ms/50))
    
    plt.plot(time_ms, volt_a, label='Healthy Cell (Grade A)', color='#2ecc71', linewidth=3)
    plt.plot(time_ms, volt_r, label='Degraded Cell (Grade R)', color='#e74c3c', linewidth=3)
    
    plt.axvspan(0, 2000, color='gray', alpha=0.1, label='1A Constant Current Load Applied')
    
    plt.title('Simulated Discharge Curves (1C Load Test)', fontweight='bold')
    plt.xlabel('Time (milliseconds)')
    plt.ylabel('Battery Voltage (V)')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, '03_discharge_curve_sim.png'), dpi=300)
    plt.close()

if __name__ == "__main__":
    print("Generating Academic/Poster Visualizations...")
    
    # Use real data if you saved it from the machine, otherwise generate mock
    df = generate_mock_data()
    df.to_csv(os.path.join(OUTPUT_DIR, "grading_dataset_log.csv"), index=False)
    print("- Dataset saved to CSV.")
    
    plot_grade_distribution(df)
    print("- Generated: Grade Distribution (Bar Chart)")
    
    plot_fusion_scatter(df)
    print("- Generated: AI Fusion Scatter Plot")
    
    plot_discharge_curve_simulation()
    print("- Generated: Discharge Curve Simulation")
    
    print(f"All graphs successfully generated in the '{OUTPUT_DIR}' directory.")
    print("These high-resolution (300 DPI) images are ready for your KIWIE poster/paper.")
