@echo off
:: compress_pdf.bat – Drag a PDF file onto this icon to compress it.
:: Keeps the console open so you can see the results.

title PDF Compressor
cd /d "%~dp0"
python "%~dp0compress_pdf.py" "%~1"
pause
