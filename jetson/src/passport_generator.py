import os
from fpdf import FPDF
from datetime import datetime

class BatteryPassport:
    def __init__(self, output_dir="passports"):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def generate_pdf(self, battery_id, grade, vision_score, volt, curr, soh, image_path):
        pdf = FPDF()
        pdf.add_page()
        
        # Header
        pdf.set_font("Arial", 'B', 20)
        pdf.cell(200, 10, txt="RECELL-AI | Digital Battery Passport", ln=True, align='C')
        
        # Subheader
        pdf.set_font("Arial", 'I', 12)
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pdf.cell(200, 10, txt=f"Generated on: {date_str}", ln=True, align='C')
        pdf.ln(10)

        # Battery Photo
        if os.path.exists(image_path):
            pdf.image(image_path, x=75, y=40, w=60)
            pdf.ln(70) # Move cursor below image
        else:
            pdf.cell(200, 10, txt="[No Photo Available]", ln=True, align='C')
            pdf.ln(10)

        # Details
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(100, 10, txt=f"Battery ID: {battery_id}", ln=True)
        pdf.cell(100, 10, txt=f"Final Grade: {grade}", ln=True)
        
        pdf.set_font("Arial", '', 12)
        pdf.ln(5)
        pdf.cell(100, 10, txt=f"Vision Score (Physical): {vision_score:.2f} / 1.00", ln=True)
        pdf.cell(100, 10, txt=f"Measured Voltage: {volt:.2f} V", ln=True)
        pdf.cell(100, 10, txt=f"Measured Current: {curr:.2f} A", ln=True)
        pdf.cell(100, 10, txt=f"Estimated SoH: {soh:.2f} %", ln=True)
        
        # Footer Note
        pdf.ln(20)
        pdf.set_font("Arial", 'I', 10)
        pdf.cell(200, 10, txt="This document verifies the automated testing of second-life batteries.", ln=True, align='C')

        file_path = os.path.join(self.output_dir, f"Passport_{battery_id}.pdf")
        pdf.output(file_path)
        return file_path
