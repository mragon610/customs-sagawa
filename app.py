import streamlit as st
import pandas as pd
import requests
import re
import os
import json
from thefuzz import fuzz
from io import BytesIO

# Cấu hình file lưu tiến trình
BACKUP_FILE = "sagawa_backup.json"

st.set_page_config(page_title="Sagawa HQ Tool Pro", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 1rem; max-width: 98%; }
    div[data-testid="stTextInput"] { margin-bottom: -15px; } 
    h1, h2, h3, h4 { margin-bottom: 0px; padding-bottom: 0px; }
    </style>
""", unsafe_allow_html=True)

# ================= QUẢN LÝ LƯU TRỮ (AUTO-SAVE) =================
def save_progress():
    """Lưu trạng thái làm việc ra ổ cứng để chống mất dữ liệu khi F5"""
    data = {
        'current_row': st.session_state['current_row'],
        'processed_results': st.session_state['processed_results'],
        'updated_db_rows': st.session_state['updated_db_rows']
    }
    with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)

def load_progress():
    """Tải lại trạng thái làm việc từ ổ cứng"""
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return None

def reset_progress():
    """Xóa file lưu tạm để bắt đầu file mới"""
    if os.path.exists(BACKUP_FILE):
        os.remove(BACKUP_FILE)
    st.session_state['current_row'] = 0
    st.session_state['processed_results'] = []
    st.session_state['updated_db_rows'] = []
    st.session_state['hojin'] = ""
    st.rerun()

# KHỞI TẠO SESSION TỪ BACKUP NẾU CÓ
if 'initialized' not in st.session_state:
    backup = load_progress()
    if backup:
        st.session_state['current_row'] = backup.get('current_row', 0)
        st.session_state['processed_results'] = backup.get('processed_results', [])
        st.session_state['updated_db_rows'] = backup.get('updated_db_rows', [])
        if st.session_state['current_row'] > 0:
            st.toast("♻️ Đã khôi phục phiên làm việc trước đó thành công!", icon="✅")
    else:
        st.session_state['current_row'] = 0
        st.session_state['processed_results'] = []
        st.session_state['updated_db_rows'] = []
        
    st.session_state['initialized'] = True
    st.session_state['hojin'] = ""

# Sidebar Menu Cài đặt
with st.sidebar:
    st.markdown("### ⚙️ Cài đặt & Tiện ích")
    if st.button("🔄 Xóa tiến trình cũ & Làm file mới", use_container_width=True):
        reset_progress()
    st.info("💡 Nếu bạn làm file mới vào hôm sau, hãy bấm nút Xóa tiến trình ở trên để tool quay về dòng 0.")

# ================= TỪ ĐIỂN CHUẨN HÓA TÊN TRƯỜNG & TỔ CHỨC ĐẶC BIỆT =================
SPECIAL_MAPPINGS = {
    "YOKKAICHI UNIV": {
        "hq_name": "YOKKAICHI UNIVERSITY",
        "kanji": "三重県四日市市萱生町1200"
    },
    "EHLE GAKKO": {
        "hq_name": "EHLE INSTITUTE",
        "kanji": "大阪府大阪市浪速区難波中3-9-1"
    }
}

# ================= HÀM XỬ LÝ TÊN SAGAWA THÔNG MINH =================
def format_sagawa_short_name(cty_name, nguoi_name):
    cty = str(cty_name).upper().strip()
    nguoi = str(nguoi_name).upper().strip()
    
    if nguoi in ["NAN", "NONE", "0", ""]: 
        nguoi = ""
    else:
        nguoi = re.sub(r'\b(MR|MS|MRS|SAMA|ATTN)\b\.?', '', nguoi).replace("/", "").strip()
    
    replacements = {
        "KABUSHIKIGAISHA": "KK", "KYOUDOU KUMIAI": "KK", "KYODO KUMIAI": "KK",
        "COOPERATIVE": "COOP", "ASSOCIATION": "ASSOC", "INTERNATIONAL": "INTL",
        "TECHNOLOGY": "TECH", "KAISHA": "", "CO., LTD.": "KK", "CO.,LTD.": "KK",
        "CO LTD": "KK", "LTD.": "", "INC.": "", "CORPORATION": "", "CORP.": ""
    }
    for old, new in replacements.items():
        cty = cty.replace(old, new)
        
    cty = re.sub(r'\s+', ' ', cty).strip()
    
    if nguoi: return f"{cty}/{nguoi}"
    else: return cty

def boc_tach_cnee(raw_h, raw_aa):
    cty = str(raw_h).strip().upper()
    pb = ""
    nguoi = str(raw_aa).strip().upper()
    if nguoi and nguoi not in ["NAN", "NONE", "0", ""]:
        nguoi = re.sub(r'\b(MR|MS|MRS|SAMA|ATTN)\b\.?', '', nguoi).replace("/", "").strip()
    else:
        nguoi = ""
    return cty, pb, nguoi

def fix_zipcode(raw_zip):
    clean = str(raw_zip).replace("-", "").replace(".0", "").strip()
    if clean in ["nan", "none", ""]: return ""
    return clean.zfill(7) 

def get_kanji_address(zipcode):
    try:
        res = requests.get(f"https://zipcloud.ibsnet.co.jp/api/search?zipcode={zipcode}", timeout=3)
        data = res.json()
        if data['status'] == 200 and data['results']:
            addr = data['results'][0]
            return f"{addr['address1']}{addr['address2']}{addr['address3']}"
    except: pass
    return "" 

def auto_find_hojinbango(company_name, kanji_location):
    query = f'"{company_name}" "{kanji_location}" 法人番号'
    url = f"https://www.google.com/search?q={query}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}
    try:
        html = requests.get(url, headers=headers, timeout=5).text
        matches = re.findall(r'(?:法人|番号).*?(\d{13})', html)
        if matches: return matches[0]
        backup = re.findall(r'\b\d{13}\b', html)
        if backup: return backup[0]
    except: pass
    return ""

def find_best_match(raw_cnee, raw_addr, raw_zip, df_db):
    for key, val in SPECIAL_MAPPINGS.items():
        if key in raw_cnee.upper():
            return {
                'score': 100,
                'kanji': val['kanji'],
                'realtime': "",
                'hojin': "",
                'hq_name': val['hq_name']
            }

    if df_db is None or df_db.empty: return None
    query = f"{raw_cnee} {raw_addr}".lower()
    best_score, best_row = 0, None
    for idx, row in df_db.iterrows():
        db_cnee = str(row.iloc[1]) if pd.notna(row.iloc[1]) else ""
        db_addr = str(row.iloc[2]) if pd.notna(row.iloc[2]) else ""
        db_zip = fix_zipcode(row.iloc[3])
        zip_bonus = 20 if raw_zip != "" and raw_zip == db_zip else 0
        score = fuzz.token_set_ratio(query, f"{db_cnee} {db_addr}".lower()) + zip_bonus
        if score > best_score:
            best_score = score
            best_row = row
    if best_score >= 80:
        return {
            'score': min(best_score, 100),
            'kanji': str(best_row.iloc[5]) if pd.notna(best_row.iloc[5]) else "", 
            'realtime': str(best_row.iloc[6]) if pd.notna(best_row.iloc[6]) else "", 
            'hojin': str(best_row.iloc[7]) if pd.notna(best_row.iloc[7]) else "", 
            'hq_name': str(best_row.iloc[8]) if pd.notna(best_row.iloc[8]) else "" 
        }
    return None

# ================= GIAO DIỆN CHÍNH =================
st.markdown("#### 📂 KHU VỰC NẠP DỮ LIỆU")
col_up1, col_up2 = st.columns(2)
with col_up1:
    db_file = st.file_uploader("1. Kéo thả Database gốc", type=["xlsx", "xlsm", "xls"])
with col_up2:
    sagawa_file = st.file_uploader("2. Kéo thả File Sagawa thô", type=["xlsx", "xlsm", "xls"])

if db_file and sagawa_file:
    if 'df_sagawa' not in st.session_state:
        st.session_state['df_sagawa'] = pd.read_excel(sagawa_file, header=2)
        st.session_state['df_db'] = pd.read_excel(db_file, header=None)
    
    df_sg = st.session_state['df_sagawa']
    df_db = st.session_state['df_db']
    total_rows = len(df_sg)
    curr_idx = st.session_state['current_row']
    
    if curr_idx < total_rows:
        current_data = df_sg.iloc[curr_idx]
        
        raw_h = str(current_data.iloc[7]) if pd.notna(current_data.iloc[7]) else ""
        raw_i = str(current_data.iloc[8]) if pd.notna(current_data.iloc[8]) else ""
        raw_j = str(current_data.iloc[9]) if pd.notna(current_data.iloc[9]) else ""
        raw_k = str(current_data.iloc[10]) if pd.notna(current_data.iloc[10]) else ""
        raw_aa = str(current_data.iloc[26]) if len(current_data) > 26 and pd.notna(current_data.iloc[26]) else ""
        
        if raw_aa in ["nan", "none", "0", "0.0"]: raw_aa = ""
        
        raw_zip = fix_zipcode(raw_j)
        cty_auto, pb_auto, nguoi_auto = boc_tach_cnee(raw_h, raw_aa)
        
        kanji_loc = get_kanji_address(raw_zip)
        match_result = find_best_match(raw_h, raw_i, raw_zip, df_db)
        
        def_hq_name = match_result['hq_name'] if match_result else cty_auto
        def_kanji = match_result['kanji'] if match_result else kanji_loc
        def_realtime = match_result['realtime'] if match_result else ""
        if str(def_realtime).lower() in ["nan", "none"]: def_realtime = ""
        
        def_hojin = st.session_state['hojin']
        if not def_hojin and match_result and match_result['hojin']:
            def_hojin = str(match_result['hojin'])
            if def_hojin.lower() in ["nan", "none"]: def_hojin = ""
            
        st.markdown(f"---")
        st.markdown(f"### ⚡ ĐANG XỬ LÝ KHÁCH HÀNG ({curr_idx + 1} / {total_rows})")

        col_trai, col_phai = st.columns([4, 6])

        with col_trai:
            st.markdown("📦 **DỮ LIỆU GỐC TỪ SAGAWA**")
            st.text_input("CNEE gốc (Cột H):", value=raw_h, disabled=True)
            st.text_input("Địa chỉ thô (Cột I):", value=raw_i, disabled=True)
            st.text_input("Zipcode (Cột J):", value=raw_zip, disabled=True)
            st.text_input("Cột K:", value=raw_k, disabled=True)
            st.text_input("Liên hệ (Cột AA):", value=raw_aa, disabled=True)
            
            st.markdown("🔍 **TÌM KIẾM THỦ CÔNG**")
            search_name = re.sub(r'(?i)\b(CO\.,?\s*LTD\.?|INC\.?|CORP\.?)\b', '', cty_auto).strip()
            tim_kiem = f"法人番号 {search_name} {kanji_loc}" 
            link_google = f"https://www.google.com/search?q={tim_kiem}"
            st.markdown(f'<a href="{link_google}" target="_blank"><button style="background-color:#4285F4; color:white; padding:5px 10px; border:none; border-radius:4px; width:100%; cursor:pointer;">Mở Web tra Pháp nhân: {kanji_loc}</button></a>', unsafe_allow_html=True)

        with col_phai:
            if match_result: st.success(f"💡 Đã tìm thấy dữ liệu cũ khớp {match_result['score']}%")
            else: st.warning("⚠️ Khách hàng mới, chưa có trong Database!")
                
            if st.button("🤖 Auto-Fill (Tìm tự động Hojinbango bằng Google)", use_container_width=True):
                with st.spinner("Đang dò tìm..."):
                    found_hojin = auto_find_hojinbango(search_name, kanji_loc)
                    if found_hojin: st.session_state['hojin'] = found_hojin
                    else: st.session_state['hojin'] = "" 
                    st.rerun() 
            
            inp_cty = st.text_input("1. Công Ty:", value=cty_auto)
            inp_pb = st.text_input("2. Phòng Ban:", value=pb_auto)
            inp_nguoi = st.text_input("3. Tên Người:", value=raw_aa if raw_aa not in ["nan", "none", "0"] else "")
            
            c_e, c_h = st.columns(2)
            final_e = format_sagawa_short_name(inp_cty, inp_nguoi)
            
            inp_e = c_e.text_input("Cột E (Sagawa chuẩn):", value=final_e)
            inp_h = c_h.text_input("Cột H (Tên HQ Full chuẩn):", value=def_hq_name)

            c_i, c_ac, c_ad = st.columns([2, 1, 1])
            inp_i = c_i.text_input("Cột I (Địa chỉ Kanji chuẩn):", value=def_kanji)
            inp_ac = c_ac.text_input("Cột AC (Realtime):", value=def_realtime) 
            inp_ad = c_ad.text_input("Cột AD (Hojinbango):", value=def_hojin)

            st.markdown("<br>", unsafe_allow_html=True)
            btn1, btn2 = st.columns(2)
            
            row_result = {
                "Cột E (Sagawa)": inp_e,
                "Cột H (輸入者名)": inp_h,
                "Cột I (輸入者住所)": inp_i,
                "Cột AC (リアルタイム口座)": inp_ac,
                "Cột AD (NACCS/法人番号)": inp_ad
            }
            
            if btn1.button("🟢 NEXT (Bỏ qua, không cập nhật DB)", use_container_width=True):
                st.session_state['processed_results'].append(row_result)
                st.session_state['current_row'] += 1
                st.session_state['hojin'] = "" 
                save_progress() # KÍCH HOẠT LƯU TIẾN TRÌNH
                st.rerun() 
                
            if btn2.button("🟡 CẬP NHẬT VÀO DATABASE & NEXT", use_container_width=True):
                st.session_state['processed_results'].append(row_result)
                new_row = [
                    None, raw_h, raw_i, raw_j, raw_k, inp_i, inp_ac, inp_ad, inp_h
                ]
                st.session_state['updated_db_rows'].append(new_row)
                st.session_state['current_row'] += 1
                st.session_state['hojin'] = ""
                save_progress() # KÍCH HOẠT LƯU TIẾN TRÌNH
                st.rerun()
    else:
        st.success("🎉 CHÚC MỪNG BẠN ĐÃ XỬ LÝ XONG TOÀN BỘ FILE SAGAWA!")
        
        col_dl1, col_dl2 = st.columns(2)
        
        # 1. TẢI FILE KẾT QUẢ SAGAWA & HẢI QUAN
        df_output = pd.DataFrame(st.session_state['processed_results'])
        out_buf = BytesIO()
        with pd.ExcelWriter(out_buf, engine='openpyxl') as writer:
            df_output.to_excel(writer, index=False, sheet_name='Ket_Qua')
        out_buf.seek(0)
        
        with col_dl1:
            st.download_button(
                label="📥 1. TẢI FILE KẾT QUẢ HOÀN CHỈNH (.xlsx)",
                data=out_buf,
                file_name="Ket_Qua_Sagawa_HaiQuan.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
        # 2. TẢI FILE DATABASE ĐÃ CẬP NHẬT MỚI
        with col_dl2:
            if st.session_state['updated_db_rows']:
                df_updated_db = pd.DataFrame(st.session_state['updated_db_rows'])
                db_buf = BytesIO()
                with pd.ExcelWriter(db_buf, engine='openpyxl') as writer:
                    df_updated_db.to_excel(writer, index=False, header=False)
                db_buf.seek(0)
                
                st.download_button(
                    label="📥 2. TẢI DATABASE BỔ SUNG MỚI (.xlsx)",
                    data=db_buf,
                    file_name="Database_Da_Cap_Nhat.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            else:
                st.info("💡 Không có dòng dữ liệu nào được cập nhật mới trong phiên này.")