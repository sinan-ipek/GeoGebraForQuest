@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo GeoGebraForQuest PC v0.14.0 - XR GPU Performance Test
echo ============================================================
echo.
echo Bu test GeoGebra ve ana PC uygulamasini ACMAZ.
echo Yalnizca su yolu olcer:
echo   RTX GPU -^> D3D11 -^> OpenXR -^> Meta Link -^> Quest

echo.
echo Testten once:
echo   1. Quest'i Link / Air Link ile PC'ye baglayin.
echo   2. Meta Quest Link ortaminda headset'i aktif tutun.
echo   3. Mumkunse Meta Link refresh rate ayarini 90 Hz yapin.
echo.
echo Test 30 saniye surecek.
echo Quest icinde hareket eden imlec ve stereo test paneli gorulmelidir.
echo.
pause

echo.
echo Test basliyor...
"%~dp0GeoGebraForQuestPC.XR.PerfTest.exe" --seconds 30
set EXITCODE=%ERRORLEVEL%

echo.
echo ============================================================
if "%EXITCODE%"=="0" (
  echo Test tamamlandi.
) else (
  echo Test hata ile bitti. Exit code: %EXITCODE%
)
echo.
echo Bu iki dosyayi ayni klasorde bulacaksiniz:
echo   GeoGebraForQuestPC.XR.PerfTest.log
echo   GeoGebraForQuestPC.XR.PerfTest.csv
echo.
echo Sonraki analiz icin bu iki dosyayi ChatGPT'ye yukleyin.
echo ============================================================
echo.
pause
exit /b %EXITCODE%
