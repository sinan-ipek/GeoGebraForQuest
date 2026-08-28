# GeoGebraForQuest PC v0.1.0

Bu dal, `stable-v0.9.29-palette` tabanlı ilk Windows/PC prototipidir.

## Bu sürümün amacı

Önce PC tarafındaki temel kararı gerçek uygulama üzerinde test etmek:

- Quest uygulamasında kullanılan patched GeoGebra Web3D motorunu Windows'ta yerel çalıştırmak.
- WebView2'nin büyük pencere / 1080p / 1440p / 4K / ultrawide kullanımını doğrulamak.
- Fiziksel klavye, mouse, sağ tık, wheel ve GeoGebra masaüstü kullanım rahatlığını doğrulamak.
- Yerel `.ggb` açma ve kaydetmeyi doğrulamak.
- GeoGebra'nın online/login popup akışının Windows WebView2 içinde çalışmasını doğrulamak.
- Quest uygulamasındaki aynı stereo kaynak hattından gelen LEFT/RIGHT eye karelerini PC tarafında almak.
- Bu kareleri B panelinde SBS olarak göstererek stereo pipeline'ın PC'de de üretildiğini doğrulamak.

## v0.1'de henüz olmayan

**Quest / Meta Link / SteamVR / OpenXR çıkışı bu sürümde henüz yoktur.**

Bu bilinçli bir aşamadır. Önce Web tabanlı PC sürümünün performansı, çözünürlüğü ve kullanım rahatlığı test edilecek. Test başarılıysa aynı L/R frame kaynağı v0.2'de OpenXR/PCVR sunum katmanına bağlanacak.

## Terminoloji

- app / uygulama = GeoGebraForQuest PC
- A = GeoGebra Panel
- B = Stereo Panel
- C = Beyaz Panel
- 3D grafik = stereo olmayan normal GeoGebra 3D bölgesi
- quest uygulaması = Android/Quest üzerinde çalışan GeoGebraForQuest

## Gereksinimler

Windows 10/11 x64 üzerinde:

1. Git
2. Python 3
3. Java/JDK (GeoGebra source build için)
4. .NET 8 SDK
5. Microsoft Edge WebView2 Runtime (Windows 11'de normalde zaten bulunur)

## Build

Depoyu bu daldan alın:

```powershell
git clone -b pc-v0.1.0-shell https://github.com/sinan-ipek/GeoGebraForQuest.git
cd GeoGebraForQuest
```

Patched GeoGebra Web3D'yi Windows üzerinde derleyin:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build-geogebra-pc.ps1
```

Ardından PC uygulamasını publish edin:

```powershell
powershell -ExecutionPolicy Bypass -File .\pc\build.ps1
```

Çıktı:

```text
dist\GeoGebraForQuest-PC-v0.1.0-win-x64\GeoGebraForQuestPC.exe
dist\GeoGebraForQuest-PC-v0.1.0-win-x64.zip
```

İlk komutu ayrıca çalıştırmak istemezseniz `pc\build.ps1`, GeoGebra paketi eksikse onu otomatik olarak hazırlar.

## İlk test

1. `GeoGebraForQuestPC.exe` açın.
2. Pencerenin ekranı tam ve keskin kullandığını kontrol edin.
3. Grafik, Grafik 2, 3D grafik, Cebir vb. görünümleri açıp pencereyi farklı boyutlara getirin.
4. Mouse, sağ tık, wheel ve klavyeyi deneyin.
5. `Yerel Aç` ile büyük bir `.ggb` dosyası açın.
6. `Farklı Kaydet` ile tekrar `.ggb` kaydedin.
7. 3D grafik açıldığında B'de L/R görüntülerinin gelmesini bekleyin.
8. B'nin altındaki `Stereo frames:` sayacının artıp artmadığını kontrol edin.
9. Ağır dosyalarda CPU/GPU/RAM ve akıcılığı klasik GeoGebra Desktop ile karşılaştırın.

## Mimari

```text
Patched GeoGebra Web3D (aynı Quest source pipeline)
                 |
              WebView2
                 |
        GeoGebraForQuest PC
          /             \
 A: interactive UI      B: L/R SBS preview
 keyboard + mouse       native WinForms control
```

`quest-stereo-layout.js`, GeoGebra renderer tarafından oluşturulan `ggq-renderer-left-eye` ve `ggq-renderer-right-eye` canvas'larını okumaya devam eder. Android `QuestBridge` yerine v0.1'de WebView2 `postMessage` bridge'i kullanılır.

Bu sayede v0.2'de Quest çıkışı eklenirken GeoGebra tarafındaki stereo hesaplamayı yeniden yazmak yerine PC'de zaten alınan L/R kareler yeni output backend'e bağlanabilir.
