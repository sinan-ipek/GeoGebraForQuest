# GeoGebraForQuest v0.2

Quest 3 için yerel GeoGebra + aynı 3B Grafik alanında gerçek stereo portal prototipi.

## Kullanıcı deneyimi

- Uygulama açıldığında bildiğimiz GeoGebra Classic görünür.
- Ayrı bir VR düğmesi veya ayrı bir VR arayüzü yoktur.
- GeoGebra'nın 3B Grafik görünümündeki projeksiyon menüsü aynen kullanılır.
- Eski anaglif/gözlük simgesi GeoGebraForQuest içinde **Stereo 3D / Quest headset** simgesine dönüştürülür.
- Bu simge seçildiğinde yeni pencere veya ikinci Activity açılmaz.
- Yalnızca mevcut GeoGebra 3B Grafik WebGL alanı transparan hale gelir ve arkasında Meta Spatial SDK'nın gerçek stereo geometrisi görünür.
- GeoGebra'nın cebir paneli, menüleri, slider'ları, giriş alanı ve diğer 2B arayüzü çalışmaya devam eder.
- Stereo kapatıldığında aynı 3B Grafik alanı tekrar normal GeoGebra renderına döner.

## Mimari

Quest'teki sıradan Android/Horizon 2B paneli iki göze ayrı görüntü veremediği için uygulama v0.2'den itibaren Spatial SDK'yı başlangıçtan kullanır. Ancak passthrough açık tutulur ve kullanıcıya yalnızca tek bir normal GeoGebra paneli gösterilir. Spatial katman, sadece 3B Grafik penceresinin transparan bölümünde görünür.

WebView ile native Spatial katmanı arasındaki köprü şunları canlı eşitler:

- 3B grafik pencere dikdörtgeni
- GeoGebra 3B kamera/orijin/ölçek bilgisi
- desteklenen geometrik nesneler
- Stereo 3D açık/kapalı durumu

v0.2 native aynalama desteği:

- noktalar
- doğru parçaları
- doğrular
- ışınlar
- Sphere(...) küreleri
- çokgen kenarları
- üç noktayla tanımlı düzlemler
- XYZ eksenleri

Bu sürümün amacı önce **"aynı GeoGebra 3B penceresinin gerçek stereoya dönüşmesi"** mimarisini Quest üzerinde doğrulamaktır. Daha karmaşık GeoGebra 3B nesneleri sonraki sürümlerde eklenecektir.

## Yerel GeoGebra

GitHub Actions derlemesi sırasında `tools/get-geogebra.sh`, GeoGebra Math Apps Bundle'ını indirip APK assets klasörüne ekler. WebView içerikleri Android `WebViewAssetLoader` üzerinden yerel HTTPS-benzeri origin ile çalışır.

## Derleme

Her `main` push'unda ve `main` hedefli pull request'te GitHub Actions debug APK üretir.

## Lisans

Bu depo kişisel/teknik prototip geliştirme içindir. GeoGebra ve Meta Spatial SDK'nın kendi lisans koşulları geçerlidir.
