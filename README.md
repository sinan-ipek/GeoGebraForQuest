# GeoGebraForQuest v0.1

Quest 3 için GeoGebra tabanlı yerel/spatial prototip.

Bu ilk sürüm şunu kanıtlamayı hedefler:

- Uygulama normal Horizon OS 2D paneli olarak açılır.
- Panel içinde GeoGebra Classic çalışır.
- 🥽 düğmesi mevcut `.ggb` durumunu kaydedip Spatial moda geçer.
- Spatial modda aynı 2D GeoGebra arayüzü kullanılmaya devam eder.
- Grafik alanının arkasında Quest'in gerçek stereo renderer'ıyla demo küre + XYZ eksenleri görünür.
- `2D` düğmesi çalışmayı kaydedip normal panel moduna döner.

## Yerel GeoGebra

GitHub Actions derlemesi sırasında `tools/get-geogebra.sh` GeoGebra Math Apps Bundle'ı indirip APK'nın assets klasörüne ekler. Böylece temel GeoGebra motoru APK içinde yerel bulunur. `index.html` yine de yerel paket eksikse resmi CDN'i yedek olarak deneyebilir.

## Derleme

Her `main` push'unda GitHub Actions otomatik olarak debug APK üretir ve `GeoGebraForQuest-debug-apk` adlı artifact olarak yayınlar.

## v0.1 sınırı

Portal içindeki küre/eksenler şimdilik demo native nesnelerdir. Bir sonraki adım GeoGebra'nın gerçek 3B construction nesnelerini native stereo renderera canlı bağlamaktır.

## Lisans

Bu depo kişisel/teknik prototip geliştirme içindir. GeoGebra ve Meta Spatial SDK'nın kendi lisans koşulları geçerlidir.
