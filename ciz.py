#!/usr/bin/env python3
"""Kapak hattı: siteden bekleyen listeyi al → Chromium'da sablon.html ile çiz → WebP → siteye yükle.

  python ciz.py ornek <json> <klasor>   # yerel deneme: JSON listesini çiz, dosyaya yaz
  python ciz.py calistir                # Actions: SITE + YOL ortam değişkenleri, kimlik OIDC

Kimlik: GitHub Actions OIDC jetonu (audience=qv3-norra). Gizli anahtar yok; site yalnız
bu deponun main dalından gelen jetonu kabul eder.
SINIR: bir koşuda en fazla kapak (varsayılan 400) · ARA: yüklemeler arası sn (varsayılan 1.5)
"""
import io, json, os, pathlib, sys, time, urllib.request, urllib.error
from PIL import Image
from playwright.sync_api import sync_playwright

KOK = pathlib.Path(__file__).resolve().parent
SABLON = (KOK / 'sablon.html').as_uri()
AUD = 'qv3-norra'
UA = 'qv3-norra/1.0 (+github actions)'
RTL = ('ar', 'ur', 'ug', 'fa')


def ciz(sayfa, v):
    """Tek kapak → WebP bayt. Sığmazsa ValueError."""
    v.setdefault('rtl', v['dil'] in RTL)
    sonuc = sayfa.evaluate('v => ciz(v)', v)
    if not sonuc.get('ok'):
        raise ValueError(f"başlık sığmadı ({sonuc})")
    png = sayfa.locator('#k').screenshot(type='png')
    im = Image.open(io.BytesIO(png)).convert('RGB')
    cikti = io.BytesIO()
    im.save(cikti, 'WEBP', quality=72, method=6)
    return cikti.getvalue(), sonuc


def tarayici(p):
    b = p.chromium.launch()
    s = b.new_page(viewport={'width': 1200, 'height': 675}, device_scale_factor=1)
    s.goto(SABLON)
    s.wait_for_function('typeof ciz === "function"')
    return b, s


def ornek(json_yol, klasor):
    veriler = json.loads(pathlib.Path(json_yol).read_text(encoding='utf-8'))
    hedef = pathlib.Path(klasor); hedef.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b, s = tarayici(p)
        for i, v in enumerate(veriler):
            ad = f"{i:02d}-{v['dil']}.webp"
            try:
                veri, sonuc = ciz(s, v)
                (hedef / ad).write_bytes(veri)
                print(ad, len(veri) // 1024, 'KB', sonuc)
            except Exception as h:
                print(ad, 'HATA', h)
        b.close()


# ---------------------------------------------------------------- site
_jeton = {'deger': None, 'zaman': 0}


def jeton():
    if _jeton['deger'] and time.time() - _jeton['zaman'] < 240:
        return _jeton['deger']
    url = os.environ['ACTIONS_ID_TOKEN_REQUEST_URL'] + '&audience=' + AUD
    r = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']})
    with urllib.request.urlopen(r, timeout=30) as y:
        _jeton['deger'] = json.loads(y.read())['value']
    _jeton['zaman'] = time.time()
    return _jeton['deger']


def istek(yol, yontem='GET', govde=None, tur=None):
    site = os.environ['SITE'].rstrip('/')
    r = urllib.request.Request(site + yol, data=govde, method=yontem)
    r.add_header('X-DK-Kapak-Jeton', jeton())
    r.add_header('User-Agent', UA)
    r.add_header('Cache-Control', 'no-cache')
    if tur:
        r.add_header('Content-Type', tur)
    for deneme in range(3):
        try:
            with urllib.request.urlopen(r, timeout=60) as y:
                return json.loads(y.read().decode('utf-8'))
        except urllib.error.HTTPError as h:
            if h.code in (502, 503, 504, 508) and deneme < 2:   # sunucu meşgul: bekle
                time.sleep(30 * (deneme + 1)); continue
            raise RuntimeError(f'{yontem} → HTTP {h.code}')
        except urllib.error.URLError:
            if deneme < 2:
                time.sleep(20); continue
            raise RuntimeError(f'{yontem} → bağlantı yok')


def calistir():
    kok = os.environ.get('YOL', '/wp-json/dkr/v1/kapak')
    sinir = int(os.environ.get('SINIR', '400'))
    ara = float(os.environ.get('ARA', '1.5'))
    yapilan = hatali = 0
    try:
        liste = istek(f'{kok}/bekleyen?adet=25')
    except RuntimeError as h:
        print(f'liste alınamadı ({h}) — uç henüz yok ya da site meşgul; sonraki koşuda tekrar.')
        return
    with sync_playwright() as p:
        b, s = tarayici(p)
        atla = set()
        while yapilan < sinir:
            ogeler = [o for o in liste.get('ogeler', []) if o['id'] not in atla]
            print(f"bekleyen {liste.get('kalan')} · bu tur {len(ogeler)}")
            if not ogeler:
                break
            for v in ogeler:
                if yapilan >= sinir:
                    break
                try:
                    veri, sonuc = ciz(s, v)
                    istek(f"{kok}/{v['id']}", 'POST', veri, 'image/webp')
                    yapilan += 1
                    print(f"  ✓ {v['id']} {v['dil']} {len(veri)//1024} KB ({sonuc['satir']} satır, {sonuc['punto']} pt)")
                except Exception as h:
                    hatali += 1; atla.add(v['id'])
                    print(f"  ✗ {v['id']} {v['dil']}: {h}")
                    if hatali >= 10:
                        print('10 hata — durdu.'); b.close(); sys.exit(1)
                time.sleep(ara)
            try:
                liste = istek(f'{kok}/bekleyen?adet=25')
            except RuntimeError as h:
                print(f'liste alınamadı ({h})'); break
        b.close()
    print(f'Bitti: {yapilan} kapak, {hatali} hata.')
    if hatali and not yapilan:
        sys.exit(1)


if __name__ == '__main__':
    if len(sys.argv) >= 4 and sys.argv[1] == 'ornek':
        ornek(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 2 and sys.argv[1] == 'calistir':
        calistir()
    else:
        print(__doc__)
