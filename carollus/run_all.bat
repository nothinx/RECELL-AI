@echo off
REM RECELL-AI / Carollus - pipeline 1-klik (Windows)
REM Jalankan dari DALAM folder carollus\ :  run_all.bat
cd /d "%~dp0"

echo === [1/4] Install dependencies ===
pip install -r requirements.txt || goto :err

echo === [2/4] Konversi model .pt -^> .onnx (ringan) ===
python scripts\export_onnx.py --weights models\best_cls.pt --imgsz 224 || goto :err

echo === [3/4] Buat semua visual evaluasi (confusion matrix dll) ===
python scripts\evaluate.py --data ..\datasets\capture --model models\best_cls.onnx --max-per-class 120 || goto :err

echo === [4/4] Tes deploy pada 1 sample ===
python scripts\deploy_onnx.py --source sample_images\SEHAT_sample.jpg || goto :err

echo.
echo SELESAI. Lihat hasil visual di folder results\
goto :eof

:err
echo [GAGAL] Ada langkah yang error. Cek pesan di atas.
exit /b 1
