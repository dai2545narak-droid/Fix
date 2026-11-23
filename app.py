import os
import io
import time
import base64
import streamlit as st
from PIL import Image
from dotenv import load_dotenv
from openai import OpenAI

# 1. โหลด API Key (รองรับทั้งไฟล์ .env และ st.secrets)
load_dotenv()
api_key = os.getenv("OPENROUTER_API_KEY")

if not api_key:
    try:
        api_key = st.secrets.get("OPENROUTER_API_KEY")
    except Exception:
        api_key = None

st.set_page_config(
    page_title="FixVision AI - ผู้ช่วยวิเคราะห์งานซ่อม",
    page_icon="🔧",
    layout="wide"
)

st.title("🔧 FixVision AI: ระบบวิเคราะห์อุปกรณ์ชำรุด")
st.caption("ขับเคลื่อนด้วย OpenRouter Vision AI — ถ่ายรูปหรืออัปโหลดภาพจุดที่เสียหายเพื่อวิเคราะห์อาการและวิธีซ่อม")

if not api_key:
    api_key = st.sidebar.text_input("ใส่ OpenRouter API Key (sk-or-v1-...):", type="password")
    if not api_key:
        st.warning("กรุณาใส่ OpenRouter API Key ในไฟล์ .env หรือแถบด้านซ้ายเพื่อเริ่มต้นใช้งาน")
        st.stop()

# เชื่อมต่อ OpenRouter ผ่าน OpenAI SDK
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
)

# 2. คำสั่งควบคุมพฤติกรรม AI
SYSTEM_INSTRUCTION = """
คุณคือวิศวกรและช่างซ่อมบำรุงผู้เชี่ยวชาญ หน้าที่ของคุณคือวิเคราะห์รูปภาพอุปกรณ์ที่ชำรุดของผู้ใช้
เมื่อได้รับรูปภาพและอาการเบื้องต้น ให้วิเคราะห์และตอบตามหัวข้อต่อไปนี้อย่างชัดเจน:

1. **อุปกรณ์และชิ้นส่วนที่พบ:** (ระบุชื่ออุปกรณ์และชิ้นส่วนที่ปรากฏในภาพ)
2. **การวิเคราะห์ความเสียหาย:** (อธิบายสิ่งที่ผิดปกติ รอยไหม้ การแตกหัก หรือจุดที่น่าสงสัย)
3. **สรุปการประเมิน:** (ระบุชัดเจนว่า "ซ่อมเองได้" / "ควรเปลี่ยนอะไหล่ใหม่" / "ต้องส่งช่างผู้เชี่ยวชาญ" พร้อมเหตุผลและประเมินค่าใช้จ่ายคร่าวๆ เป็นเงินบาท)
4. **เครื่องมือและอุปกรณ์ที่ต้องเตรียม:** (ลิสต์รายการเครื่องมือที่จำเป็น)
5. **ขั้นตอนการซ่อมทีละขั้น:** (อธิบายเป็นข้อๆ 1, 2, 3... ให้ทำตามได้จริง)
6. **⚠️ ข้อควรระวังด้านความปลอดภัย:** (ระบุความเสี่ยง เช่น ไฟฟ้าดูด ความร้อน สารเคมี)
7. **ข้อมูลที่ต้องการเพิ่มเติม (ถ้ามี):** (หากภาพไม่ชัด ให้ระบุว่าควรถ่ายซูมจุดไหนเพิ่ม หรือต้องวัดค่าอะไรเพิ่มเติม)

กฎสำคัญ: หากเป็นอุปกรณ์ไฟฟ้าแรงสูง แก๊ส หรือมีความเสี่ยงสูง ห้ามแนะนำให้ผู้ใช้รื้อซ่อมเองโดยเด็ดขาด ให้แนะนำส่งช่างเท่านั้น
"""

# 3. ฟังก์ชันแปลงรูปภาพเป็น Base64 (พร้อมย่อขนาดภาพไม่ให้ใหญ่เกินไป)
def encode_image_to_base64(pil_image, max_size=1024):
    img_copy = pil_image.copy()
    if img_copy.mode in ("RGBA", "P"):
        img_copy = img_copy.convert("RGB")
    img_copy.thumbnail((max_size, max_size))
    buffered = io.BytesIO()
    img_copy.save(buffered, format="JPEG", quality=85)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

# 4. ฟังก์ชันเรียกใช้งาน OpenRouter พร้อมระบบสลับโมเดลสำรอง
def ask_openrouter_with_fallback(messages):
    # รายชื่อโมเดล Vision บน OpenRouter (สามารถเปลี่ยนหรือเพิ่มชื่อโมเดลได้ตามต้องการ)
    models_to_try = [
        "google/gemini-2.5-flash",
        "openai/gpt-4o-mini",
        "qwen/qwen2.5-vl-72b-instruct:free",
        "google/gemini-2.0-flash-exp:free"
    ]
    last_error = None

    for model_name in models_to_try:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.2,
                extra_headers={
                    "HTTP-Referer": "http://localhost:8501",
                    "X-Title": "FixVision AI"
                }
            )
            return response.choices[0].message.content, model_name
        except Exception as e:
            last_error = e
            time.sleep(1)
            continue
    raise last_error

# 5. ส่วนรับข้อมูล (ซ้าย: รูปภาพ / ขวา: ผลการวิเคราะห์)
col1, col2 = st.columns([1, 1.3], gap="large")

with col1:
    st.subheader("1. นำเข้าภาพจุดที่เสียหาย")
    input_method = st.radio(
        "เลือกวิธีนำเข้าภาพ:",
        ["อัปโหลดรูปภาพ / ถ่ายจากมือถือ", "เปิดกล้องเว็บแคม"],
        horizontal=True
    )

    image_file = None
    if input_method == "อัปโหลดรูปภาพ / ถ่ายจากมือถือ":
        image_file = st.file_uploader("เลือกไฟล์ภาพ หรือกดถ่ายภาพ (JPG, PNG)", type=["jpg", "jpeg", "png"])
    else:
        image_file = st.camera_input("ถ่ายรูปอุปกรณ์ตรงส่วนที่พัง")

    symptoms = st.text_area(
        "2. อธิบายอาการเพิ่มเติม (ช่วยให้แม่นยำขึ้น):",
        placeholder="เช่น เปิดไม่ติด, มีกลิ่นไหม้, มีเสียงดังแกรกๆ, ทำตกพื้น..."
    )

    analyze_btn = st.button("🔍 เริ่มวิเคราะห์อาการเสีย", type="primary", width="stretch")

    img = None
    if image_file:
        img = Image.open(image_file)
        st.image(img, caption="ภาพที่ใช้วิเคราะห์", width="stretch")

# 6. ส่วนประมวลผลและแสดงผลลัพธ์
with col2:
    st.subheader("3. ผลการวิเคราะห์และแนวทางแก้ไข")

    if "diagnosis" not in st.session_state:
        st.session_state.diagnosis = None
    if "used_model" not in st.session_state:
        st.session_state.used_model = None
    if "img_base64" not in st.session_state:
        st.session_state.img_base64 = None
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    if analyze_btn:
        if not img:
            st.error("กรุณาอัปโหลดหรือถ่ายรูปอุปกรณ์ก่อนกดวิเคราะห์ครับ")
        else:
            with st.spinner("กำลังส่งภาพให้วิศวกร AI ผ่าน OpenRouter ตรวจสอบ..."):
                try:
                    img_b64 = encode_image_to_base64(img)
                    st.session_state.img_base64 = img_b64

                    user_prompt = f"อาการเพิ่มเติมจากผู้ใช้: {symptoms if symptoms else 'ไม่ได้ระบุ (วิเคราะห์จากภาพเป็นหลัก)'}"

                    messages = [
                        {"role": "system", "content": SYSTEM_INSTRUCTION},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": user_prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
                                }
                            ]
                        }
                    ]

                    result_text, used_model = ask_openrouter_with_fallback(messages)
                    st.session_state.diagnosis = result_text
                    st.session_state.used_model = used_model
                    st.session_state.chat_history = []
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาดในการเชื่อมต่อ OpenRouter: {e}")

    # แสดงผลคำตอบ
    if st.session_state.diagnosis:
        st.caption(f"⚡ วิเคราะห์โดยโมเดล: `{st.session_state.used_model}`")
        st.markdown(st.session_state.diagnosis)

        st.divider()
        # 7. ระบบถาม-ตอบเพิ่มเติมกับช่าง AI
        st.subheader("💬 สอบถามช่าง AI เพิ่มเติม")
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if follow_up := st.chat_input("ถามต่อ เช่น 'อะไหล่ตัวนี้หาซื้อได้ที่ไหน' หรือ 'ถอดน็อตตัวไหนก่อน'"):
            st.session_state.chat_history.append({"role": "user", "content": follow_up})
            with st.chat_message("user"):
                st.markdown(follow_up)

            with st.chat_message("assistant"):
                with st.spinner("กำลังตอบคำถาม..."):
                    try:
                        chat_messages = [
                            {"role": "system", "content": SYSTEM_INSTRUCTION},
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": f"ผลการวิเคราะห์ก่อนหน้า:\n{st.session_state.diagnosis}\n\nคำถามเพิ่มเติม: {follow_up}"},
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": f"data:image/jpeg;base64,{st.session_state.img_base64}"}
                                    }
                                ]
                            }
                        ]
                        reply_text, _ = ask_openrouter_with_fallback(chat_messages)
                        st.markdown(reply_text)
                        st.session_state.chat_history.append({"role": "assistant", "content": reply_text})
                    except Exception as e:
                        st.error(f"เกิดข้อผิดพลาดในการตอบกลับ: {e}")