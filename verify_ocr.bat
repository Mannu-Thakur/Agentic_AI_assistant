@echo off
title OCR Verification
echo ==========================================
echo        OCR SYSTEM VERIFICATION
echo ==========================================
echo.

echo [1/9] Python Version
python --version
echo.

echo [2/9] Tesseract Location
where tesseract
echo.

echo [3/9] Tesseract Version
tesseract --version
echo.

echo [4/9] Poppler - pdfinfo
where pdfinfo
echo.

echo [5/9] Poppler - pdftoppm
where pdftoppm
echo.

echo [6/9] Python OCR Libraries
python -c "import pytesseract,cv2,PIL,numpy,pdf2image; print('pytesseract:',pytesseract.__version__ if hasattr(pytesseract,'__version__') else 'OK'); print('OpenCV:',cv2.__version__); print('Pillow:',PIL.__version__); print('NumPy:',numpy.__version__); print('pdf2image: OK')"
echo.

echo [7/9] Tesseract From Python
python -c "import pytesseract; print('Executable:',pytesseract.pytesseract.tesseract_cmd); print('Version:',pytesseract.get_tesseract_version())"
echo.

echo [8/9] Environment Variables
echo TESSERACT_CMD=%TESSERACT_CMD%
echo REQUIRE_OCR=%REQUIRE_OCR%
echo.

echo [9/9] OCR Test Suite
pytest backend/tests/test_ocr_pipeline.py -v
echo.

echo ==========================================
echo Verification Finished
echo ==========================================
pause