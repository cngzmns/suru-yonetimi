import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from PIL import Image
import hashlib
import io

st.set_page_config(page_title="Tam Donanımlı Sürü Yönetimi", page_icon="🐄", layout="wide")

# --- VERİTABANI BAĞLANTISI ---
@st.cache_resource
def get_engine():
    return create_engine(st.secrets["DATABASE_URL"], pool_pre_ping=True)

engine = get_engine()

def hash_sifre(sifre: str) -> str:
    return hashlib.sha256(sifre.encode("utf-8")).hexdigest()

def init_db():
    with engine.begin() as conn:
        # Kullanıcılar Tablosu (Çoklu Kullanıcı & Rol Yetkilendirme)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS kullanicilar (
                kullanici_adi TEXT PRIMARY KEY,
                ad_soyad TEXT,
                sifre_hash TEXT,
                rol TEXT DEFAULT 'Personel',
                aktif INTEGER DEFAULT 1
            )
        """))
        # Hayvanlar Tablosu (Fotoğraf, Anne/Baba Küpe, Laktasyon, Canlı Ağırlık vb.)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS hayvanlar (
                kupe_no TEXT PRIMARY KEY,
                isim TEXT,
                irk TEXT,
                cinsiyet TEXT,
                grup TEXT,
                padok TEXT,
                dogum_tarihi TEXT,
                anne_kupe TEXT,
                baba_kupe TEXT,
                laktasyon_no INTEGER DEFAULT 0,
                durum TEXT DEFAULT 'Aktif',
                notlar TEXT,
                foto BYTEA
            )
        """))
        # Üreme ve Gebelik Tablosu (Kızgınlık, Tohumlama, Kuruya Çıkış, Doğum)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ureme (
                id SERIAL PRIMARY KEY,
                kupe_no TEXT,
                tohumlama_tarihi TEXT,
                boga_kodu TEXT,
                gebelik_durumu TEXT,
                sonraki_kizginlik TEXT,
                kuruya_cikis TEXT,
                tahmini_dogum TEXT,
                kaydeden TEXT
            )
        """))
        # Süt Verimi Tablosu
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sut (
                id SERIAL PRIMARY KEY,
                kupe_no TEXT,
                tarih TEXT,
                sabah REAL,
                aksam REAL,
                toplam REAL,
                kaydeden TEXT
            )
        """))
        # Besi Tartım Tablosu
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tartim (
                id SERIAL PRIMARY KEY,
                kupe_no TEXT,
                tarih TEXT,
                agirlik REAL,
                gcaa REAL,
                kaydeden TEXT
            )
        """))
        # Sağlık, Aşı & Arınma Süresi Tablosu
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS saglik (
                id SERIAL PRIMARY KEY,
                kupe_no TEXT,
                tarih TEXT,
                islem_turu TEXT,
                ilac_adi TEXT,
                aciklama TEXT,
                sut_arinma_bitis TEXT,
                et_arinma_bitis TEXT,
                hatirlatma_tarihi TEXT,
                kaydeden TEXT
            )
        """))
        # Yem & Malzeme Stok Takibi
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stok (
                id SERIAL PRIMARY KEY,
                tarih TEXT,
                urun_adi TEXT,
                islem_tipi TEXT,
                miktar_kg REAL,
                birim_fiyat REAL,
                aciklama TEXT,
                kaydeden TEXT
            )
        """))
        # Rasyon Maliyeti
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS rasyon_maliyet (
                id SERIAL PRIMARY KEY,
                tarih TEXT,
                grup TEXT,
                hayvan_sayisi INTEGER,
                gunluk_kisi_basi_tl REAL,
                toplam_gunluk_tl REAL,
                detay TEXT,
                kaydeden TEXT
            )
        """))
        # Gelir - Gider Finans Tablosu
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS finans (
                id SERIAL PRIMARY KEY,
                tarih TEXT,
                tur TEXT,
                kategori TEXT,
                tutar REAL,
                aciklama TEXT,
                kaydeden TEXT
            )
        """))

        # Varsayılan Yönetici Hesabı (Yoksa Secrets'taki şifreyle oluşturur)
        res = conn.execute(text("SELECT COUNT(*) FROM kullanicilar")).scalar()
        if res == 0:
            varsayilan_sifre = st.secrets.get("UYGULAMA_SIFRESI", "123456")
            conn.execute(text("""
                INSERT INTO kullanicilar (kullanici_adi, ad_soyad, sifre_hash, rol, aktif)
                VALUES ('admin', 'İşletme Yöneticisi', :sh, 'Yönetici', 1)
            """), {"sh": hash_sifre(varsayilan_sifre)})

init_db()

# --- ÇOKLU KULLANICI GİRİŞ EKRANI ---
if "kullanici" not in st.session_state:
    st.session_state.kullanici = None

if st.session_state.kullanici is None:
    col_bos1, col_giris, col_bos2 = st.columns([1, 1.2, 1])
    with col_giris:
        st.title("🔒 Çiftlik Sürü Yönetim Sistemi")
        st.caption("Lütfen kullanıcı adınız ve şifreniz ile giriş yapın.")
        with st.form("giris_formu"):
            k_adi = st.text_input("Kullanıcı Adı (Varsayılan: admin)")
            sifre = st.text_input("Şifre", type="password")
            if st.form_submit_button("Giriş Yap", use_container_width=True):
                with engine.begin() as conn:
                    user = conn.execute(text("""
                        SELECT kullanici_adi, ad_soyad, sifre_hash, rol, aktif
                        FROM kullanicilar WHERE kullanici_adi = :k
                    """), {"k": k_adi.strip().lower()}).fetchone()
                
                if user and user[4] == 1 and user[2] == hash_sifre(sifre):
                    st.session_state.kullanici = {
                        "kullanici_adi": user[0],
                        "ad_soyad": user[1],
                        "rol": user[3]
                    }
                    st.rerun()
                else:
                    st.error("Kullanıcı adı veya şifre hatalı ya da hesap pasif!")
    st.stop()

aktif_kullanici = st.session_state.kullanici

# --- YARDIMCI FONKSİYONLAR ---
def resmi_sikistir(uploaded_file) -> bytes:
    img = Image.open(uploaded_file)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.thumbnail((600, 600))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75)
    return buf.getvalue()

# --- SOL MENÜ ---
st.sidebar.title("🐄 Sürü Yönetimi PRO")
st.sidebar.markdown(f"👤 **{aktif_kullanici['ad_soyad']}** (`{aktif_kullanici['rol']}`)")

col_btn1, col_btn2 = st.sidebar.columns(2)
if col_btn1.button("🔄 Yenile", use_container_width=True):
    st.rerun()
if col_btn2.button("🚪 Çıkış", use_container_width=True):
    st.session_state.kullanici = None
    st.rerun()

st.sidebar.divider()

menuler = [
    "📊 Özet, Uyarılar & Grafikler",
    "🐮 Hayvan Kartı, Fotoğraf & Liste",
    "🥛 Süt & Üreme (Kızgınlık/Doğum)",
    "⚖️ Besi Tartım & GCAA Analizi",
    "🌾 Rasyon & Yem Stok Takibi",
    "💉 Sağlık, Aşı & Arınma Süresi",
    "💰 Gelir - Gider & Kârlılık",
    "📥 Toplu Excel Aktar & Raporla",
    "✏️ Kayıt Düzenle / Sil"
]

if aktif_kullanici["rol"] == "Yönetici":
    menuler.append("👥 Kullanıcı & Yetki Yönetimi")

menu = st.sidebar.radio("Modül Seçin:", menuler)

# --- 1. ÖZET, UYARILAR & GRAFİKLER ---
if menu == "📊 Özet, Uyarılar & Grafikler":
    st.title("📊 İşletme Özeti, Günlük Alarmlar ve Verim Grafikleri")
    
    df_hayvan = pd.read_sql("SELECT * FROM hayvanlar WHERE durum='Aktif'", engine)
    df_sut = pd.read_sql("SELECT * FROM sut", engine)
    df_ureme = pd.read_sql("SELECT * FROM ureme", engine)
    df_saglik = pd.read_sql("SELECT * FROM saglik", engine)
    df_finans = pd.read_sql("SELECT * FROM finans", engine)

    bugun = datetime.now().date()
    bugun_str = bugun.strftime("%Y-%m-%d")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Aktif Sürü", f"{len(df_hayvan)} Baş")
    c2.metric("Süt Grubu", f"{len(df_hayvan[df_hayvan['grup'] == 'Süt'])} Baş")
    c3.metric("Besi Grubu", f"{len(df_hayvan[df_hayvan['grup'] == 'Besi'])} Baş")
    
    bugun_sut = df_sut[df_sut["tarih"] == bugun_str]["toplam"].sum() if not df_sut.empty else 0.0
    c4.metric("Bugünkü Süt", f"{bugun_sut:.1f} Lt")

    ay_basi = bugun.replace(day=1).strftime("%Y-%m-%d")
    if not df_finans.empty:
        ay_gelir = df_finans[(df_finans["tarih"] >= ay_basi) & (df_finans["tur"] == "Gelir")]["tutar"].sum()
        ay_gider = df_finans[(df_finans["tarih"] >= ay_basi) & (df_finans["tur"] == "Gider")]["tutar"].sum()
        c5.metric("Bu Ay Net Durum", f"{(ay_gelir - ay_gider):,.0f} TL")
    else:
        c5.metric("Bu Ay Net Durum", "0 TL")

    st.divider()
    st.subheader("🚨 Kritik Takvim ve Arınma Uyarıları (Önümüzdeki 15 Gün)")
    onbes_gun = bugun + timedelta(days=15)
    alarm_var = False

    # Üreme Uyarıları (21. Gün Kızgınlık Kontrolü, Kuruya Çıkış, Doğum)
    if not df_ureme.empty:
        for _, row in df_ureme.iterrows():
            if row["gebelik_durumu"] == "Beklemede" and row.get("sonraki_kizginlik"):
                kiz_t = datetime.strptime(row["sonraki_kizginlik"], "%Y-%m-%d").date()
                if bugun - timedelta(days=2) <= kiz_t <= onbes_gun:
                    st.info(f"🔄 **Kızgınlık Kontrolü (21. Gün):** `{row['kupe_no']}` küpeli hayvanı tohumlama sonrası tekrar kızgınlık açısından gözlemleyin: **{row['sonraki_kizginlik']}**")
                    alarm_var = True

            if row["gebelik_durumu"] in ("Gebe", "Beklemede"):
                kuru_t = datetime.strptime(row["kuruya_cikis"], "%Y-%m-%d").date()
                dogum_t = datetime.strptime(row["tahmini_dogum"], "%Y-%m-%d").date()
                if bugun <= kuru_t <= onbes_gun:
                    st.warning(f"🟡 **Kuruya Ayırma:** `{row['kupe_no']}` küpeli ineğin kuruya çıkma tarihi: **{row['kuruya_cikis']}**")
                    alarm_var = True
                if bugun <= dogum_t <= onbes_gun:
                    st.error(f"🔴 **Yaklaşan Doğum:** `{row['kupe_no']}` küpeli ineğin tahmini doğum tarihi: **{row['tahmini_dogum']}**")
                    alarm_var = True

    # Sağlık & Antibiyotik Arınma Süresi Uyarıları
    if not df_saglik.empty:
        for _, row in df_saglik.iterrows():
            if row.get("sut_arinma_bitis"):
                sut_ar = datetime.strptime(row["sut_arinma_bitis"], "%Y-%m-%d").date()
                if bugun <= sut_ar:
                    st.error(f"🚫 **SÜT DÖKME UYARISI (Arınma Süresi):** `{row['kupe_no']}` ({row.get('ilac_adi', '')}) - Sütü **{row['sut_arinma_bitis']}** tarihine kadar tanka katmayın!")
                    alarm_var = True
            if row.get("et_arinma_bitis"):
                et_ar = datetime.strptime(row["et_arinma_bitis"], "%Y-%m-%d").date()
                if bugun <= et_ar:
                    st.warning(f"⚠️ **KESİM YASAĞI (Et Arınma):** `{row['kupe_no']}` ({row.get('ilac_adi', '')}) - **{row['et_arinma_bitis']}** tarihine kadar kesime gönderilemez.")
                    alarm_var = True
            if row.get("hatirlatma_tarihi"):
                hat_t = datetime.strptime(row["hatirlatma_tarihi"], "%Y-%m-%d").date()
                if bugun <= hat_t <= onbes_gun:
                    st.info(f"💉 **Aşı / Tedavi Hatırlatması:** `{row['kupe_no']}` - {row['islem_turu']} ({row['aciklama']}) | Tarih: **{row['hatirlatma_tarihi']}**")
                    alarm_var = True

    if not alarm_var:
        st.success("✅ Önümüzdeki 15 gün içinde kritik bir uyarı veya arınma süresi kısıtlaması bulunmuyor.")

    st.divider()
    g1, g2 = st.columns(2)
    with g1:
        st.subheader("📈 Günlük Toplam Süt Üretimi (Son 30 Kayıt)")
        if not df_sut.empty:
            gunluk_sut = df_sut.groupby("tarih")["toplam"].sum().reset_index().sort_values("tarih").tail(30)
            st.line_chart(gunluk_sut.set_index("tarih")["toplam"])
        else:
            st.caption("Henüz süt verimi kaydı girilmedi.")

    with g2:
        st.subheader("🐮 Sürü Dağılımı (Grup Bazlı)")
        if not df_hayvan.empty:
            grup_dagilim = df_hayvan["grup"].value_counts()
            st.bar_chart(grup_dagilim)
        else:
            st.caption("Henüz hayvan kaydı girilmedi.")

# --- 2. HAYVAN KARTI, FOTOĞRAF & LİSTE ---
elif menu == "🐮 Hayvan Kartı, Fotoğraf & Liste":
    st.title("🐮 Hayvan Kartı, Fotoğraf ve Soy Kütüğü")
    tab_kart, tab_yeni = st.tabs(["🔍 Hayvan Kartı & Fotoğraf Görüntüle", "➕ Yeni Hayvan Ekle / Güncelle"])

    with tab_kart:
        df_h = pd.read_sql("SELECT kupe_no, isim, irk, cinsiyet, grup, padok, dogum_tarihi, anne_kupe, baba_kupe, laktasyon_no, durum, notlar FROM hayvanlar ORDER BY kupe_no", engine)
        if not df_h.empty:
            filtre_grup = st.selectbox("Gruba Göre Filtrele", ["Tümü"] + df_h["grup"].dropna().unique().tolist())
            df_goster = df_h if filtre_grup == "Tümü" else df_h[df_h["grup"] == filtre_grup]
            
            secilen_kupe = st.selectbox("Detaylı Kartını Görmek İstediğiniz Hayvan:", df_goster["kupe_no"].tolist())
            if secilen_kupe:
                with engine.begin() as conn:
                    detay = conn.execute(text("SELECT * FROM hayvanlar WHERE kupe_no = :k"), {"k": secilen_kupe}).mappings().fetchone()
                
                col_foto, col_bilgi = st.columns([1, 2])
                with col_foto:
                    if detay["foto"]:
                        st.image(bytes(detay["foto"]), caption=f"{detay['kupe_no']} ({detay['isim'] or 'İsimsiz'})", use_container_width=True)
                    else:
                        st.info("Bu hayvan için henüz fotoğraf yüklenmemiş.")
                    
                    yeni_foto = st.file_uploader("Fotoğraf Yükle / Değiştir", type=["jpg", "jpeg", "png"], key="kart_foto")
                    if yeni_foto and st.button("Fotoğrafı Kaydet"):
                        foto_bytes = resmi_sikistir(yeni_foto)
                        with engine.begin() as conn:
                            conn.execute(text("UPDATE hayvanlar SET foto = :f WHERE kupe_no = :k"), {"f": foto_bytes, "k": secilen_kupe})
                        st.success("Fotoğraf güncellendi!")
                        st.rerun()

                with col_bilgi:
                    st.subheader(f"Küpe No: {detay['kupe_no']} {f'- {detay["isim"]}' if detay['isim'] else ''}")
                    b1, b2, b3 = st.columns(3)
                    b1.write(f"**Irk:** {detay['irk']}")
                    b2.write(f"**Cinsiyet:** {detay['cinsiyet']}")
                    b3.write(f"**Durum:** {detay['durum']}")

                    b4, b5, b6 = st.columns(3)
                    b4.write(f"**Grup:** {detay['grup']}")
                    b5.write(f"**Padok:** {detay['padok'] or '-'}")
                    b6.write(f"**Laktasyon:** {detay['laktasyon_no']}")

                    b7, b8, b9 = st.columns(3)
                    b7.write(f"**Doğum Tarihi:** {detay['dogum_tarihi']}")
                    b8.write(f"**Anne Küpe:** {detay['anne_kupe'] or '-'}")
                    b9.write(f"**Baba Küpe/Boğa:** {detay['baba_kupe'] or '-'}")
                    
                    if detay["notlar"]:
                        st.info(f"📝 **Notlar:** {detay['notlar']}")

            st.divider()
            st.subheader("Tüm Sürü Tablosu")
            st.dataframe(df_goster, use_container_width=True)
        else:
            st.info("Sistemde kayıtlı hayvan bulunmuyor. 'Yeni Hayvan Ekle' sekmesinden ekleyebilirsiniz.")

    with tab_yeni:
        with st.form("hayvan_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            kupe = c1.text_input("Küpe No * (Örn: TR4500012345)")
            isim = c2.text_input("Hayvan Adı / Takma Adı (İsteğe Bağlı)")
            irk = c3.selectbox("Irk", ["Holstein", "Simental", "Montofon", "Angus", "Şarole", "Limuzin", "Belçika Mavisi", "Yerli Kara", "Melez"])
            
            c4, c5, c6 = st.columns(3)
            cinsiyet = c4.selectbox("Cinsiyet", ["Dişi", "Erkek"])
            grup = c5.selectbox("Sürü Grubu", ["Süt", "Besi", "Düve", "Buzağı", "Kuru Dönem"])
            padok = c6.text_input("Padok / Bölme (Örn: Süt-1, Besi-2)")
            
            c7, c8, c9 = st.columns(3)
            dogum_t = c7.date_input("Doğum Tarihi", datetime.now())
            anne_k = c8.text_input("Anne Küpe No")
            baba_k = c9.text_input("Baba Küpe / Boğa Kodu")

            c10, c11, c12 = st.columns(3)
            laktasyon = c10.number_input("Laktasyon Sayısı (Doğum Sayısı)", min_value=0, step=1)
            durum = c11.selectbox("Durum", ["Aktif", "Satıldı", "Kesime Gitti", "Öldü"])
            foto_dosya = c12.file_uploader("Hayvan Fotoğrafı (Kameradan veya Galeriden)", type=["jpg", "jpeg", "png"])
            
            notlar = st.text_input("Özel Notlar (Mizaç, kronik durum vb.)")
            
            if st.form_submit_button("Hayvanı Kaydet"):
                if kupe.strip():
                    foto_bytes = resmi_sikistir(foto_dosya) if foto_dosya else None
                    with engine.begin() as conn:
                        if foto_bytes is not None:
                            conn.execute(text("""
                                INSERT INTO hayvanlar (kupe_no, isim, irk, cinsiyet, grup, padok, dogum_tarihi, anne_kupe, baba_kupe, laktasyon_no, durum, notlar, foto)
                                VALUES (:k, :is, :i, :c, :g, :p, :d, :ak, :bk, :lk, :du, :nt, :ft)
                                ON CONFLICT (kupe_no) DO UPDATE SET
                                isim=:is, irk=:i, cinsiyet=:c, grup=:g, padok=:p, dogum_tarihi=:d, anne_kupe=:ak, baba_kupe=:bk, laktasyon_no=:lk, durum=:du, notlar=:nt, foto=:ft
                            """), {
                                "k": kupe.strip().upper(), "is": isim, "i": irk, "c": cinsiyet, "g": grup,
                                "p": padok, "d": dogum_t.strftime("%Y-%m-%d"), "ak": anne_k.upper(),
                                "bk": baba_k.upper(), "lk": laktasyon, "du": durum, "nt": notlar, "ft": foto_bytes
                            })
                        else:
                            conn.execute(text("""
                                INSERT INTO hayvanlar (kupe_no, isim, irk, cinsiyet, grup, padok, dogum_tarihi, anne_kupe, baba_kupe, laktasyon_no, durum, notlar)
                                VALUES (:k, :is, :i, :c, :g, :p, :d, :ak, :bk, :lk, :du, :nt)
                                ON CONFLICT (kupe_no) DO UPDATE SET
                                isim=:is, irk=:i, cinsiyet=:c, grup=:g, padok=:p, dogum_tarihi=:d, anne_kupe=:ak, baba_kupe=:bk, laktasyon_no=:lk, durum=:du, notlar=:nt
                            """), {
                                "k": kupe.strip().upper(), "is": isim, "i": irk, "c": cinsiyet, "g": grup,
                                "p": padok, "d": dogum_t.strftime("%Y-%m-%d"), "ak": anne_k.upper(),
                                "bk": baba_k.upper(), "lk": laktasyon, "du": durum, "nt": notlar
                            })
                    st.success(f"{kupe.strip().upper()} başarıyla kaydedildi!")
                else:
                    st.error("Lütfen küpe numarası girin.")

# --- 3. SÜT & ÜREME TAKİBİ ---
elif menu == "🥛 Süt & Üreme (Kızgınlık/Doğum)":
    st.title("🥛 Süt Verimi ve Üreme / Gebelik Yönetimi")
    tab1, tab2 = st.tabs(["🥛 Günlük Süt Girişi", "🧬 Tohumlama, Kızgınlık & Gebelik"])
    
    hayvanlar = pd.read_sql("SELECT kupe_no FROM hayvanlar WHERE durum='Aktif' AND cinsiyet='Dişi' ORDER BY kupe_no", engine)["kupe_no"].tolist()

    with tab1:
        with st.form("sut_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            s_kupe = c1.selectbox("Hayvan Küpe No", hayvanlar) if hayvanlar else c1.text_input("Küpe No")
            s_tarih = c2.date_input("Sağım Tarihi", datetime.now())
            sabah = c3.number_input("Sabah Sütü (Lt)", min_value=0.0, step=0.5)
            aksam = c4.number_input("Akşam Sütü (Lt)", min_value=0.0, step=0.5)
            
            if st.form_submit_button("Süt Verimini Kaydet"):
                toplam = sabah + aksam
                with engine.begin() as conn:
                    conn.execute(text("""
                        INSERT INTO sut (kupe_no, tarih, sabah, aksam, toplam, kaydeden)
                        VALUES (:k, :t, :s, :a, :top, :kay)
                    """), {"k": s_kupe, "t": s_tarih.strftime("%Y-%m-%d"), "s": sabah, "a": aksam, "top": toplam, "kay": aktif_kullanici["kullanici_adi"]})
                st.success(f"{s_kupe} için toplam {toplam} Lt süt kaydedildi.")
        
        df_s = pd.read_sql("SELECT * FROM sut ORDER BY tarih DESC, id DESC", engine)
        st.dataframe(df_s, use_container_width=True)

    with tab2:
        with st.form("ureme_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            u_kupe = c1.selectbox("Tohumlanan Hayvan", hayvanlar) if hayvanlar else c1.text_input("Küpe No")
            t_tarih = c2.date_input("Tohumlama Tarihi", datetime.now())
            boga = c3.text_input("Boğa Kodu / Adı")
            durum = c4.selectbox("Gebelik Durumu", ["Beklemede", "Gebe", "Boş"])
            
            if st.form_submit_button("Tohumlama Kaydet"):
                kizginlik = (t_tarih + timedelta(days=21)).strftime("%Y-%m-%d")
                kuru = (t_tarih + timedelta(days=220)).strftime("%Y-%m-%d")
                dogum = (t_tarih + timedelta(days=280)).strftime("%Y-%m-%d")
                with engine.begin() as conn:
                    conn.execute(text("""
                        INSERT INTO ureme (kupe_no, tohumlama_tarihi, boga_kodu, gebelik_durumu, sonraki_kizginlik, kuruya_cikis, tahmini_dogum, kaydeden)
                        VALUES (:k, :t, :b, :d, :kz, :ku, :do, :kay)
                    """), {
                        "k": u_kupe, "t": t_tarih.strftime("%Y-%m-%d"), "b": boga, "d": durum,
                        "kz": kizginlik, "ku": kuru, "do": dogum, "kay": aktif_kullanici["kullanici_adi"]
                    })
                st.success(f"Kaydedildi! 21. Gün Kontrol: {kizginlik} | Kuruya Çıkış: {kuru} | Tahmini Doğum: {dogum}")

        st.subheader("Gebelik Durumu Güncelle")
        df_u = pd.read_sql("SELECT * FROM ureme ORDER BY id DESC", engine)
        if not df_u.empty:
            g1, g2, g3 = st.columns([2, 2, 1])
            sec_id = g1.selectbox("Kayıt Seç (ID - Küpe - Tarih)", df_u.apply(lambda r: f"{r['id']} | {r['kupe_no']} ({r['tohumlama_tarihi']}) - {r['gebelik_durumu']}", axis=1))
            yeni_durum = g2.selectbox("Yeni Durum", ["Gebe", "Boş", "Doğum Yaptı", "Beklemede"])
            if g3.button("Durumu Güncelle"):
                kayit_id = int(sec_id.split(" | ")[0])
                with engine.begin() as conn:
                    conn.execute(text("UPDATE ureme SET gebelik_durumu = :d WHERE id = :id"), {"d": yeni_durum, "id": kayit_id})
                st.success("Gebelik durumu güncellendi!")
                st.rerun()

        st.dataframe(df_u, use_container_width=True)

# --- 4. BESİ TARTIM & GCAA ---
elif menu == "⚖️ Besi Tartım & GCAA Analizi":
    st.title("⚖️ Besi Canlı Ağırlık ve Günlük Ağırlık Artışı (GCAA)")
    besi_list = pd.read_sql("SELECT kupe_no FROM hayvanlar WHERE durum='Aktif' ORDER BY kupe_no", engine)["kupe_no"].tolist()

    with st.form("tartim_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        b_kupe = c1.selectbox("Hayvan Küpe No", besi_list) if besi_list else c1.text_input("Küpe No")
        tartim_t = c2.date_input("Tartım Tarihi", datetime.now())
        kilo = c3.number_input("Canlı Ağırlık (kg)", min_value=20.0, step=1.0)
        
        if st.form_submit_button("Tartımı Kaydet ve GCAA Hesapla"):
            onceki = pd.read_sql(text("SELECT tarih, agirlik FROM tartim WHERE kupe_no=:k ORDER BY tarih DESC LIMIT 1"), engine, params={"k": b_kupe})
            gcaa = 0.0
            if not onceki.empty:
                eski_t = datetime.strptime(onceki.iloc[0]["tarih"], "%Y-%m-%d").date()
                gun = (tartim_t - eski_t).days
                if gun > 0:
                    gcaa = round((kilo - onceki.iloc[0]["agirlik"]) / gun, 2)
            
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO tartim (kupe_no, tarih, agirlik, gcaa, kaydeden)
                    VALUES (:k, :t, :a, :g, :kay)
                """), {"k": b_kupe, "t": tartim_t.strftime("%Y-%m-%d"), "a": kilo, "g": gcaa, "kay": aktif_kullanici["kullanici_adi"]})
            
            if gcaa > 0:
                st.success(f"{b_kupe} tartıldı: {kilo} kg | Günlük Canlı Ağırlık Artışı (GCAA): **{gcaa} kg/gün**")
            else:
                st.info(f"{b_kupe} için tartım kaydedildi: {kilo} kg")

    df_t = pd.read_sql("SELECT * FROM tartim ORDER BY tarih DESC, id DESC", engine)
    st.dataframe(df_t, use_container_width=True)

# --- 5. RASYON & YEM STOK TAKİBİ ---
elif menu == "🌾 Rasyon & Yem Stok Takibi":
    st.title("🌾 Rasyon Maliyeti ve Yem Depo / Silaj Stok Takibi")
    tab_rasyon, tab_stok = st.tabs(["🧮 Günlük Rasyon Maliyeti", "📦 Yem & Silaj Stok Yönetimi"])

    with tab_rasyon:
        c1, c2 = st.columns(2)
        grup_adi = c1.selectbox("Rasyon Grubu", ["Sağmal İnek (Yüksek Verim)", "Sağmal İnek (Orta Verim)", "Kuru Dönem", "Besi Başlangıç", "Besi Bitiş", "Buzağı / Düve"])
        hayvan_adedi = c2.number_input("Bu Gruptaki Hayvan Sayısı", min_value=1, value=20)

        yemler = ["Mısır Silajı", "Yonca Kuru Otu", "Buğday Samanı", "Süt/Besi Fabrika Yemi", "Arpa / Mısır Ezmesi", "Küspe (Pamuk/Ayçiçeği)", "Vitamin / Mineral Premiks"]
        toplam_kisi_maliyet = 0.0
        detay_list = []

        for yem in yemler:
            col_a, col_b, col_c = st.columns([2, 1.5, 1.5])
            col_a.write(f"**{yem}**")
            miktar = col_b.number_input(f"Miktar (kg) - {yem}", min_value=0.0, step=0.5, key=f"m_{yem}")
            fiyat = col_c.number_input(f"Birim Fiyat (TL/kg) - {yem}", min_value=0.0, step=0.5, key=f"f_{yem}")
            tutar = miktar * fiyat
            toplam_kisi_maliyet += tutar
            if miktar > 0:
                detay_list.append(f"{yem}: {miktar}kg x {fiyat}TL")

        grup_toplam = toplam_kisi_maliyet * hayvan_adedi
        st.divider()
        m1, m2, m3 = st.columns(3)
        m1.metric("1 Hayvan Günlük Maliyet", f"{toplam_kisi_maliyet:.2f} TL")
        m2.metric(f"Grup Günlük ({hayvan_adedi} Baş)", f"{grup_toplam:.2f} TL")
        m3.metric("Grup Aylık (30 Gün)", f"{(grup_toplam * 30):,.2f} TL")

        if st.button("Rasyon Maliyetini Kaydet"):
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO rasyon_maliyet (tarih, grup, hayvan_sayisi, gunluk_kisi_basi_tl, toplam_gunluk_tl, detay, kaydeden)
                    VALUES (:t, :g, :h, :k, :top, :d, :kay)
                """), {
                    "t": datetime.now().strftime("%Y-%m-%d"), "g": grup_adi, "h": hayvan_adedi,
                    "k": toplam_kisi_maliyet, "top": grup_toplam, "d": ", ".join(detay_list),
                    "kay": aktif_kullanici["kullanici_adi"]
                })
            st.success("Rasyon maliyeti kaydedildi!")

        df_ras = pd.read_sql("SELECT * FROM rasyon_maliyet ORDER BY id DESC", engine)
        st.dataframe(df_ras, use_container_width=True)

    with tab_stok:
        with st.form("stok_form", clear_on_submit=True):
            s1, s2, s3, s4 = st.columns(4)
            urun = s1.selectbox("Yem / Hammadde", ["Mısır Silajı", "Yonca Kuru Otu", "Buğday Samanı", "Süt Yemi", "Besi Yemi", "Arpa Ezmesi", "Mısır Ezmesi", "Küspe", "Diğer"])
            islem = s2.selectbox("İşlem Türü", ["Stok Girişi (Alım/Hasat)", "Stok Çıkışı (Tüketim)"])
            miktar_kg = s3.number_input("Miktar (kg)", min_value=1.0, step=50.0)
            birim_tl = s4.number_input("Birim Fiyat (TL/kg)", min_value=0.0, step=0.5)
            aciklama = st.text_input("Tedarikçi / Açıklama")
            
            if st.form_submit_button("Stok Hareketini Kaydet"):
                with engine.begin() as conn:
                    conn.execute(text("""
                        INSERT INTO stok (tarih, urun_adi, islem_tipi, miktar_kg, birim_fiyat, aciklama, kaydeden)
                        VALUES (:t, :u, :is, :m, :bf, :ac, :kay)
                    """), {
                        "t": datetime.now().strftime("%Y-%m-%d"), "u": urun, "is": islem,
                        "m": miktar_kg, "bf": birim_tl, "ac": aciklama, "kay": aktif_kullanici["kullanici_adi"]
                    })
                st.success("Stok hareketi kaydedildi!")

        df_stok = pd.read_sql("SELECT * FROM stok ORDER BY id DESC", engine)
        if not df_stok.empty:
            st.subheader("📊 Güncel Depo Stok Durumu")
            girisler = df_stok[df_stok["islem_tipi"].str.contains("Girişi")].groupby("urun_adi")["miktar_kg"].sum()
            cikislar = df_stok[df_stok["islem_tipi"].str.contains("Çıkışı")].groupby("urun_adi")["miktar_kg"].sum()
            mevcut_stok = (girisler.subtract(cikislar, fill_value=0)).reset_index()
            mevcut_stok.columns = ["Ürün Adı", "Kalan Stok (kg)"]
            mevcut_stok["Kalan Stok (Ton)"] = (mevcut_stok["Kalan Stok (kg)"] / 1000).round(2)
            st.dataframe(mevcut_stok, use_container_width=True)

# --- 6. SAĞLIK, AŞI & ARINMA SÜRESİ ---
elif menu == "💉 Sağlık, Aşı & Arınma Süresi":
    st.title("💉 Sağlık, Tedavi, Aşı ve Antibiyotik Arınma Takibi")
    tum_hayvanlar = pd.read_sql("SELECT kupe_no FROM hayvanlar WHERE durum='Aktif' ORDER BY kupe_no", engine)["kupe_no"].tolist()

    with st.form("saglik_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        h_kupe = c1.selectbox("Hayvan Küpe No", tum_hayvanlar) if tum_hayvanlar else c1.text_input("Küpe No")
        islem = c2.selectbox("İşlem Türü", ["Aşılama (Şap/Brusella/LSD/Karma)", "Mastitis Tedavisi", "Metritis / Doğum Sonrası", "Ayak / Tırnak Bakımı", "Parazit Uygulaması", "Genel Tedavi / Antibiyotik"])
        ilac = c3.text_input("Kullanılan İlaç / Aşı Adı")
        
        c4, c5, c6, c7 = st.columns(4)
        u_tarih = c4.date_input("Uygulama Tarihi", datetime.now())
        sut_arinma_gun = c5.number_input("Süt Arınma Süresi (Gün)", min_value=0, step=1, help="Sütün tanka katılmayacağı gün sayısı")
        et_arinma_gun = c6.number_input("Et Arınma Süresi (Gün)", min_value=0, step=1, help="Kesim yasağı gün sayısı")
        hatirlatma_gun = c7.number_input("Tekrar / Kontrol (Gün Sonra)", min_value=0, value=14, step=1)
        
        aciklama = st.text_input("Veteriner Hekim Notu / Dozaj")

        if st.form_submit_button("Sağlık Kaydını Ekle"):
            sut_bitis = (u_tarih + timedelta(days=int(sut_arinma_gun))).strftime("%Y-%m-%d") if sut_arinma_gun > 0 else ""
            et_bitis = (u_tarih + timedelta(days=int(et_arinma_gun))).strftime("%Y-%m-%d") if et_arinma_gun > 0 else ""
            hat_tarih = (u_tarih + timedelta(days=int(hatirlatma_gun))).strftime("%Y-%m-%d") if hatirlatma_gun > 0 else ""

            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO saglik (kupe_no, tarih, islem_turu, ilac_adi, aciklama, sut_arinma_bitis, et_arinma_bitis, hatirlatma_tarihi, kaydeden)
                    VALUES (:k, :t, :i, :il, :ac, :sa, :ea, :ht, :kay)
                """), {
                    "k": h_kupe, "t": u_tarih.strftime("%Y-%m-%d"), "i": islem, "il": ilac,
                    "ac": aciklama, "sa": sut_bitis, "ea": et_bitis, "ht": hat_tarih,
                    "kay": aktif_kullanici["kullanici_adi"]
                })
            st.success("Sağlık kaydı ve arınma süresi uyarıları eklendi!")

    df_sag = pd.read_sql("SELECT * FROM saglik ORDER BY tarih DESC, id DESC", engine)
    st.dataframe(df_sag, use_container_width=True)

# --- 7. GELİR - GİDER & KÂRLILIK ---
elif menu == "💰 Gelir - Gider & Kârlılık":
    st.title("💰 İşletme Gelir - Gider ve Kârlılık Takibi")

    with st.form("finans_form", clear_on_submit=True):
        f1, f2, f3, f4 = st.columns(4)
        f_tarih = f1.date_input("Tarih", datetime.now())
        f_tur = f2.selectbox("İşlem Türü", ["Gelir", "Gider"])
        f_kat = f3.selectbox("Kategori", ["Süt Satışı", "Besi / Canlı Hayvan Satışı", "Buzağı / Damızlık Satışı", "Yem / Hammadde Alımı", "Veteriner / İlaç / Aşı", "Elektrik / Su / Mazot", "İşçilik / Bakım", "Diğer"])
        f_tutar = f4.number_input("Tutar (TL)", min_value=0.0, step=100.0)
        f_aciklama = st.text_input("Açıklama (Örn: Mandıra süt ödemesi, 2 ton arpa alımı)")

        if st.form_submit_button("Finans Kaydını Ekle"):
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO finans (tarih, tur, kategori, tutar, aciklama, kaydeden)
                    VALUES (:t, :tur, :kat, :tut, :ac, :kay)
                """), {
                    "t": f_tarih.strftime("%Y-%m-%d"), "tur": f_tur, "kat": f_kat,
                    "tut": f_tutar, "ac": f_aciklama, "kay": aktif_kullanici["kullanici_adi"]
                })
            st.success("Finans kaydı eklendi!")

    df_fin = pd.read_sql("SELECT * FROM finans ORDER BY tarih DESC, id DESC", engine)
    if not df_fin.empty:
        top_gelir = df_fin[df_fin["tur"] == "Gelir"]["tutar"].sum()
        top_gider = df_fin[df_fin["tur"] == "Gider"]["tutar"].sum()
        k1, k2, k3 = st.columns(3)
        k1.metric("Toplam Gelir", f"{top_gelir:,.2f} TL")
        k2.metric("Toplam Gider", f"{top_gider:,.2f} TL")
        k3.metric("Net Kâr / Zarar", f"{(top_gelir - top_gider):,.2f} TL")
        st.dataframe(df_fin, use_container_width=True)

# --- 8. TOPLU EXCEL AKTAR & RAPORLA ---
elif menu == "📥 Toplu Excel Aktar & Raporla":
    st.title("📥 Excel Rapor İndir ve Toplu Hayvan Yükle")
    
    st.subheader("1. Tüm Çiftlik Verilerini Excel Olarak İndir")
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.read_sql("SELECT kupe_no, isim, irk, cinsiyet, grup, padok, dogum_tarihi, anne_kupe, baba_kupe, laktasyon_no, durum, notlar FROM hayvanlar", engine).to_excel(writer, sheet_name="Hayvan_Listesi", index=False)
        pd.read_sql("SELECT * FROM sut", engine).to_excel(writer, sheet_name="Sut_Verimi", index=False)
        pd.read_sql("SELECT * FROM ureme", engine).to_excel(writer, sheet_name="Ureme_Gebelik", index=False)
        pd.read_sql("SELECT * FROM tartim", engine).to_excel(writer, sheet_name="Besi_Tartim", index=False)
        pd.read_sql("SELECT * FROM saglik", engine).to_excel(writer, sheet_name="Saglik_Asi", index=False)
        pd.read_sql("SELECT * FROM stok", engine).to_excel(writer, sheet_name="Yem_Stok", index=False)
        pd.read_sql("SELECT * FROM rasyon_maliyet", engine).to_excel(writer, sheet_name="Rasyon_Maliyet", index=False)
        pd.read_sql("SELECT * FROM finans", engine).to_excel(writer, sheet_name="Gelir_Gider", index=False)

    st.download_button(
        label="📊 Tam Çiftlik Raporunu İndir (.xlsx)",
        data=output.getvalue(),
        file_name=f"ciftlik_tam_rapor_{datetime.now().strftime('%Y_%m_%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.divider()
    st.subheader("2. Excel'den Toplu Hayvan Listesi Yükle")
    st.caption("Excel dosyanızda şu sütun başlıkları olmalıdır: `kupe_no`, `irk`, `cinsiyet`, `grup`, `padok`, `dogum_tarihi`")
    excel_yukle = st.file_uploader("Hayvan Listesi Excel Dosyası (.xlsx)", type=["xlsx"])
    if excel_yukle and st.button("Excel Verilerini Sisteme Aktar"):
        df_yukle = pd.read_excel(excel_yukle)
        eklenen = 0
        with engine.begin() as conn:
            for _, r in df_yukle.iterrows():
                if pd.notna(r.get("kupe_no")):
                    conn.execute(text("""
                        INSERT INTO hayvanlar (kupe_no, irk, cinsiyet, grup, padok, dogum_tarihi, durum)
                        VALUES (:k, :i, :c, :g, :p, :d, 'Aktif')
                        ON CONFLICT (kupe_no) DO NOTHING
                    """), {
                        "k": str(r["kupe_no"]).strip().upper(),
                        "i": str(r.get("irk", "Holstein")),
                        "c": str(r.get("cinsiyet", "Dişi")),
                        "g": str(r.get("grup", "Süt")),
                        "p": str(r.get("padok", "")),
                        "d": str(r.get("dogum_tarihi", datetime.now().strftime("%Y-%m-%d")))[:10]
                    })
                    eklenen += 1
        st.success(f"Toplam {eklenen} hayvan başarıyla içeri aktarıldı!")

# --- 9. KAYIT DÜZENLE / SİL ---
elif menu == "✏️ Kayıt Düzenle / Sil":
    st.title("✏️ Hatalı Kayıtları Silme")
    tablo_sec = st.selectbox("İşlem Yapılacak Tablo", ["hayvanlar", "sut", "ureme", "tartim", "saglik", "stok", "finans"])
    
    if tablo_sec == "hayvanlar":
        df_sil = pd.read_sql("SELECT kupe_no, isim, irk, grup, padok, durum FROM hayvanlar ORDER BY kupe_no", engine)
        st.dataframe(df_sil, use_container_width=True)
        sil_kupe = st.selectbox("Silinecek Hayvan Küpe No", df_sil["kupe_no"].tolist()) if not df_sil.empty else None
        if sil_kupe and st.button("Seçili Hayvanı Sil", type="primary"):
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM hayvanlar WHERE kupe_no = :k"), {"k": sil_kupe})
            st.success(f"{sil_kupe} silindi!")
            st.rerun()
    else:
        df_sil = pd.read_sql(f"SELECT * FROM {tablo_sec} ORDER BY id DESC LIMIT 100", engine)
        st.dataframe(df_sil, use_container_width=True)
        if not df_sil.empty:
            sil_id = st.number_input("Silinecek Kayıt ID Numarası", min_value=1, step=1)
            if st.button("Kaydı Sil", type="primary"):
                with engine.begin() as conn:
                    conn.execute(text(f"DELETE FROM {tablo_sec} WHERE id = :id"), {"id": int(sil_id)})
                st.success(f"ID {sil_id} silindi!")
                st.rerun()

# --- 10. KULLANICI & YETKİ YÖNETİMİ (SADECE YÖNETİCİ) ---
elif menu == "👥 Kullanıcı & Yetki Yönetimi" and aktif_kullanici["rol"] == "Yönetici":
    st.title("👥 Çoklu Kullanıcı ve Şifre Yönetimi")
    st.write("Aile bireyleri, veteriner hekim veya bakıcılar için ayrı kullanıcı adı ve şifre oluşturabilirsiniz. Her kayıtta hangi kullanıcının işlem yaptığı otomatik kaydedilir.")

    with st.form("kullanici_ekle_form", clear_on_submit=True):
        u1, u2, u3, u4 = st.columns(4)
        yeni_k_adi = u1.text_input("Kullanıcı Adı (Boşluksuz, küçük harf)")
        yeni_ad_soyad = u2.text_input("Ad Soyad (Örn: Veteriner Ahmet)")
        yeni_sifre = u3.text_input("Giriş Şifresi", type="password")
        yeni_rol = u4.selectbox("Yetki Rolü", ["Personel", "Yönetici"])

        if st.form_submit_button("Kullanıcı Oluştur / Şifre Güncelle"):
            if yeni_k_adi.strip() and yeni_sifre.strip():
                with engine.begin() as conn:
                    conn.execute(text("""
                        INSERT INTO kullanicilar (kullanici_adi, ad_soyad, sifre_hash, rol, aktif)
                        VALUES (:k, :ad, :sh, :r, 1)
                        ON CONFLICT (kullanici_adi) DO UPDATE SET
                        ad_soyad=:ad, sifre_hash=:sh, rol=:r, aktif=1
                    """), {
                        "k": yeni_k_adi.strip().lower(),
                        "ad": yeni_ad_soyad.strip() or yeni_k_adi.strip(),
                        "sh": hash_sifre(yeni_sifre.strip()),
                        "r": yeni_rol
                    })
                st.success(f"`{yeni_k_adi.strip().lower()}` kullanıcısı kaydedildi!")
            else:
                st.error("Kullanıcı adı ve şifre boş bırakılamaz.")

    st.subheader("Kayıtlı Kullanıcılar")
    df_users = pd.read_sql("SELECT kullanici_adi, ad_soyad, rol, aktif FROM kullanicilar", engine)
    st.dataframe(df_users, use_container_width=True)

    if not df_users.empty:
        sec_user = st.selectbox("Durumu Değiştirilecek / Silinecek Kullanıcı", df_users["kullanici_adi"].tolist())
        b1, b2 = st.columns(2)
        if b1.button("Aktif / Pasif Yap"):
            if sec_user == aktif_kullanici["kullanici_adi"]:
                st.warning("Kendi hesabınızı pasif yapamazsınız.")
            else:
                with engine.begin() as conn:
                    conn.execute(text("UPDATE kullanicilar SET aktif = 1 - aktif WHERE kullanici_adi = :k"), {"k": sec_user})
                st.rerun()
        if b2.button("Kullanıcıyı Sil"):
            if sec_user == aktif_kullanici["kullanici_adi"]:
                st.warning("Kendi hesabınızı silemezsiniz.")
            else:
                with engine.begin() as conn:
                    conn.execute(text("DELETE FROM kullanicilar WHERE kullanici_adi = :k"), {"k": sec_user})
                st.rerun()
