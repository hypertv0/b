# b — güncel spor yayın listeleri (otomatik)

Her 15 dakikada GitHub Actions çalışır, BeyazElma ailesinin **o anki güncel adresini**
(`domains.json` üzerinden) bulup canlı maçlarla spor kanallarını çözer.

- **liste.m3u** — Canlı Maçlar + Spor Kanalları (tek liste, `group-title` ile ayrık)
- **kanallar/*.m3u8** — her spor kanalı için tekil dosya

Sadece o an gerçekten `#EXTM3U` döndüren yayınlar listeye girer; ölü link yazılmaz.
