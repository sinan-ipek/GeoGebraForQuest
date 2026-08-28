# GeoGebraForQuest PC v0.1.0 build notes

The PC shell is compiled on Windows with .NET 8 and WebView2.

The patched GeoGebra Web3D bundle is deliberately built on Linux with the existing proven `tools/build-geogebra-quest.sh` pipeline. The resulting `GeoGebra` web asset directory is then passed to the Windows publish job.

This avoids changing the renderer patches or creating a second GeoGebra source pipeline merely for Windows packaging.
