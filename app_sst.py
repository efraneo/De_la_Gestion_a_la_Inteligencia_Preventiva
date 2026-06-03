import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import io
from PIL import Image
import uuid
import bcrypt
import google.generativeai as genai
from supabase import create_client, Client

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Inteligencia Preventiva SST", page_icon="🛡️", layout="wide")

# --- CONEXIÓN A LA NUBE (SUPABASE Y GEMINI) ---
# Estas claves se configuran en Streamlit Cloud (Secrets)
try:
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_key = st.secrets["SUPABASE_KEY"]
    gemini_key = st.secrets["GEMINI_API_KEY"]
    supabase: Client = create_client(supabase_url, supabase_key)
    genai.configure(api_key=gemini_key)
    vision_model = genai.GenerativeModel('gemini-1.5-flash')
except:
    st.error("⚠️ Faltan las claves secretas (Supabase/Gemini) en la configuración de Streamlit.")
    st.stop()

# [Mantén aquí tus ESTILOS CSS, init_users_db, register_user, verify_user - NO CAMBIAN]
# ... (Los omito por espacio, pero van exactamente igual que el código anterior)

# --- MOTOR DE IA PREDICTIVA (NTC 3701) ---
def predict_sst_analysis(texto_hallazgo):
    texto = texto_hallazgo.lower()
    if any(palabra in texto for palabra in ["silla", "mobiliario", "escritorio", "cama", "colchón"]):
        categoria = "Mobiliario / Ergonomía"
        analisis = {"categoria": categoria, "evento": texto_hallazgo.capitalize(), "porques": ["Por qué 1", "Por qué 2"], "causa_raiz": "Falla estructural", "actos_sub": ["550"], "condiciones_sub": ["035"], "factores_personales": ["998"], "factores_trabajo": ["300"], "acciones": [{"titulo":"Inspección","objetivo":"Retirar","actividades":"Física","responsable":"SST","frecuencia":"Mensual"}], "conclusion": "Falla mobiliario."}
    elif any(palabra in texto for palabra in ["cable", "eléctric", "toma", "enchufe", "tablero"]):
        categoria = "Riesgo Eléctrico"
        analisis = {"categoria": categoria, "evento": texto_hallazgo.capitalize(), "porques": ["Por qué 1", "Por qué 2"], "causa_raiz": "Riesgo eléctrico", "actos_sub": ["550"], "condiciones_sub": ["035"], "factores_personales": ["998"], "factores_trabajo": ["300"], "acciones": [{"titulo":"Aislamiento","objetivo":"Eliminar","actividades":"Desenergizar","responsable":"Mantenimiento","frecuencia":"Inmediata"}], "conclusion": "Riesgo eléctrico."}
    else:
        categoria = "Infraestructura / General"
        analisis = {"categoria": categoria, "evento": texto_hallazgo.capitalize(), "porques": ["Por qué 1", "Por qué 2"], "causa_raiz": "Deterioro infraestructura", "actos_sub": ["550"], "condiciones_sub": ["035"], "factores_personales": ["998"], "factores_trabajo": ["300"], "acciones": [{"titulo":"Correctiva","objetivo":"Reparar","actividades":"Evaluación","responsable":"Mantenimiento","frecuencia":"Inmediata"}], "conclusion": "Infraestructura."}
    return analisis

# --- NUEVA FUNCIÓN: GUARDAR EN LA NUBE ---
def save_to_supabase(tipo_input, descripcion, resultado, image_url=None):
    data = {
        "tipo_input": tipo_input,
        "descripcion": descripcion,
        "categoria_detectada": resultado['categoria'],
        "causa_raiz": resultado['causa_raiz'],
        "conclusion": resultado['conclusion'],
        "image_url": image_url
    }
    supabase.table('historial_ia').insert(data).execute()

# --- NUEVA FUNCIÓN: LEER DE LA NUBE ---
def load_historial_supabase():
    response = supabase.table('historial_ia').select("*").order("fecha_analisis", desc=True).execute()
    return pd.DataFrame(response.data)

# ==========================================
# APLICACIÓN PRINCIPAL (LOGUEADO)
# ==========================================
# [Asumiendo que ya pasaste el Login...]
menu = st.sidebar.radio("Navegación", ["📊 Dashboard KPIs", "🤖 IA Predictiva", "📁 Exportar Datos"])

# --- IA PREDICTIVA (LA MAGIA CON VISIÓN) ---
if menu == "🤖 IA Predictiva":
    st.title("🤖 Motor de Investigación y Predicción NTC 3701")
    
    input_type = st.radio("¿Cómo desea ingresar el hallazgo?", ("📝 Escribir Texto", "📷 Subir Imagen (IA Vision)"))
    texto_analizar = ""

    if input_type == "📝 Escribir Texto":
        texto_analizar = st.text_area("Describa el evento o condición subestándar:", height=150)
        
        if st.button("🧠 Generar Investigación") and texto_analizar:
            resultado = predict_sst_analysis(texto_analizar)
            save_to_supabase("Texto", texto_analizar, resultado)
            st.success("✅ Análisis Generado y Guardado en la Nube!")
            # [Aquí va el código para mostrar los 5 Porqués, Causas, etc...]

    elif input_type == "📷 Subir Imagen (IA Vision)":
        uploaded_file = st.file_uploader("Toma o sube una foto del acto/condición subestándar", type=['png', 'jpg', 'jpeg'])
        
        if uploaded_file is not None:
            image = Image.open(uploaded_file)
            st.image(image, caption="Imagen Cargada para Análisis de IA", use_column_width=True)
            
            if st.button("👁️ Analizar Imagen con IA"):
                with st.spinner("La IA está observando la imagen y deduciendo el riesgo..."):
                    try:
                        # 1. Gemini "mira" la foto
                        prompt_vision = "Eres un experto en Seguridad y Salud en el Trabajo (SST). Observa esta imagen de un entorno laboral. Describe en 1 o 2 oraciones concisas la condición subestándar o acto inseguro que ves. Enfócate en el riesgo principal (ej: riesgo eléctrico, mobiliario deteriorado, humedad, obstáculo en vía)."
                        response = vision_model.generate_content([prompt_vision, image])
                        texto_analizar = response.text
                        st.info(f"📝 **La IA detectó:** {texto_analizar}")
                        
                        # 2. Subir imagen a Supabase Storage
                        img_bytes = uploaded_file.getvalue()
                        file_name = f"{uuid.uuid4().hex}.jpg"
                        supabase.storage.from_("fotos-sst").upload(file_name, img_bytes, {"content-type": "image/jpeg"})
                        image_url = supabase.storage.from_("fotos-sst").get_public_url(file_name)
                        
                        # 3. Procesar con nuestro motor y guardar
                        resultado = predict_sst_analysis(texto_analizar)
                        save_to_supabase("Imagen", texto_analizar, resultado, image_url)
                        
                        st.success("✅ Análisis de Visión Generado y Guardado en la Nube!")
                        # [Aquí va el código para mostrar los 5 Porqués, Causas, etc...]
                        
                    except Exception as e:
                        st.error(f"Error al procesar la imagen con la IA: {e}")

    # --- DASHBOARD KPIs (LECTURA DESDE LA NUBE) ---
elif menu == "📊 Dashboard KPIs":
    st.title("🛡️ De la Gestión a la Inteligencia Preventiva")
    
    # Leer datos de la nube
    df_ia = load_historial_supabase()
    total_eventos_ia = len(df_ia)
    
    # Mostrar KPIs...
    st.markdown(f"Total Eventos Procesados: **{total_eventos_ia}**")
    
    if not df_ia.empty:
        # Gráfica de eventos con imagen vs texto
        st.subheader("Distribución por Tipo de Input")
        fig = px.histogram(df_ia, x="tipo_input", color="tipo_input")
        st.plotly_chart(fig)
        
        # Si quieres mostrar las imágenes en el dashboard:
        st.subheader("Últimos Hallazgos con Imágenes")
        df_con_img = df_ia[df_ia['image_url'].notna()].head(3)
        cols = st.columns(len(df_con_img))
        for idx, row in df_con_img.iterrows():
            with cols[idx]:
                st.image(row['image_url'], caption=row['categoria_detectada'])
    else:
        st.info("Aún no hay datos en la nube.")
