import sys

def test_ocr():
    print("=== TESTING AVAILABLE OCR ENGINES ===")
    
    # 1. Test rapidocr
    try:
        from rapidocr_onnxruntime import RapidOCR
        engine = RapidOCR()
        print("✔ rapidocr_onnxruntime is available!")
        return "rapidocr"
    except Exception as e:
        print(f"RapidOCR not available: {e}")

    # 2. Test Windows.Media.Ocr (WinRT / Windows 10 native OCR)
    try:
        import winrt.windows.media.ocr as ocr
        import winrt.windows.graphics.imaging as imaging
        print("✔ Windows.Media.Ocr (WinRT) is available!")
        return "winrt"
    except Exception as e:
        print(f"WinRT OCR not available: {e}")

    # 3. Test pytesseract
    try:
        import pytesseract
        print("✔ pytesseract module imported!")
        return "pytesseract"
    except Exception as e:
        print(f"pytesseract not available: {e}")

    return None

if __name__ == "__main__":
    test_ocr()
