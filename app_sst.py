import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import io
from PIL import Image
import os
import uuid
import bcrypt
import json
import base64

# --- CONFIGURACIÓN DE PÁGINA (DEBE SER LO PRIMERO) ---
st.set_page_config(page_title="Inteligencia Preventiva SST", page_icon="🛡️", layout="wide")

# --- ESTILOS CSS PRO ---
st.markdown("""
<style>
    .main { background-color: #f8f9fa; }
    .stButton>button { background-color: #0056b3; color: white; border-radius: 8px; border: none; padding: 10px 24px; }
    .stButton>button:hover { background-color: #004494; color: white; }
    .metric-card { background-color: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; }
    .kpi-value { font-size: 32px; font-weight: bold; color: #0056b3; }
    .kpi-label { font-size: 14px; color: #6c757d; }
</style>
""", unsafe_allow_html=True)

# --- CONEXIÓN A LA NUBE (SUPABASE Y GROQ IA) ---
try:
    supabase_url = st.secrets["SUPABASE_URL"].rstrip('/')
    supabase_key = st.secrets["SUPABASE_KEY"]
    groq_key = st.secrets["GROQ_API_KEY"] 
    
    from supabase import create_client, Client
    from groq import Groq
    
    supabase: Client = create_client(supabase_url, supabase_key)
    client_groq = Groq(api_key=groq_key)
    CLOUD_CONNECTED = True
except Exception as e:
    CLOUD_CONNECTED = False
    st.warning(f"⚠️ Configuración de nube incompleta. Funcionando en modo local. Error: {e}")

# --- CREAR CARPETA PARA IMAGENES LOCAL ---
if not os.path.exists("uploads"):
    os.makedirs("uploads")

# --- BASE DE DATOS SQLITE (USUARIOS) ---
def init_users_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (cedula TEXT PRIMARY KEY, nombre TEXT, fecha_nac TEXT, correo TEXT UNIQUE, celular TEXT, 
                 clave TEXT, ip_registro TEXT, ip_ultimo_acceso TEXT, fecha_registro TIMESTAMP, aprobado BOOLEAN)''')
    admin_user = "dasb1512"
    c.execute("SELECT * FROM users WHERE correo=?", (admin_user,))
    if not c.fetchone():
        hashed_clave = bcrypt.hashpw("cocolizo76".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        c.execute("""INSERT INTO users (cedula, nombre, fecha_nac, correo, celular, clave, ip_registro, ip_ultimo_acceso, fecha_registro, aprobado) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                  ('0000000', 'Administrador SST', '1990-01-01', admin_user, '3000000000', hashed_clave, '0.0.0.0', '0.0.0.0', datetime.now(), True))
    conn.commit()
    return conn

def get_client_ip():
    try:
        if hasattr(st, 'context') and st.context.headers.get("X-Forwarded-For"):
            return st.context.headers.get("X-Forwarded-For").split(',')[0]
    except:
        pass
    return "127.0.0.1"

def register_user(cedula, nombre, fecha_nac, correo, celular, clave, ip):
    conn = init_users_db()
    c = conn.cursor()
    try:
        hashed_clave = bcrypt.hashpw(clave.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        c.execute("""INSERT INTO users (cedula, nombre, fecha_nac, correo, celular, clave, ip_registro, ip_ultimo_acceso, fecha_registro, aprobado) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                  (cedula, nombre, fecha_nac, correo, celular, hashed_clave, ip, ip, datetime.now(), False))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def verify_user(correo, clave, current_ip):
    conn = init_users_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE correo=?", (correo,))
    user = c.fetchone()
    if user and bcrypt.checkpw(clave.encode('utf-8'), user[5].encode('utf-8')):
        user_data = {"cedula": user[0], "nombre": user[1], "correo": user[3], "ip_registro": user[6], "ip_ultimo_acceso": user[7], "fecha_registro": user[8], "aprobado": user[9]}
        if correo != "dasb1512" and user_data["ip_registro"] != current_ip and user_data["ip_ultimo_acceso"] != current_ip:
            return None, "⚠️ Advertencia de seguridad: Se detectó un acceso desde un dispositivo/IP diferente. Contacte al administrador."
        c.execute("UPDATE users SET ip_ultimo_acceso=? WHERE correo=?", (current_ip, correo))
        conn.commit()
        if not user_data["aprobado"]:
            fecha_reg = datetime.strptime(user_data["fecha_registro"].split('.')[0], "%Y-%m-%d %H:%M:%S")
            if datetime.now() > fecha_reg + timedelta(days=3):
                return None, "⏳ Su prueba gratuita de 3 días ha terminado. Comuníquese con ing.efrainsarmientoc@outlook.es."
        return user_data, "OK"
    return None, "❌ Usuario o clave incorrectos."

# --- MOTOR DE IA PREDICTIVA (NTC 3701 - 100% REAL CON GROQ) ---
def predict_sst_analysis(texto_hallazgo):
    prompt_ia = f"""
    Actúa como un Auditor Experto en Seguridad y Salud en el Trabajo (SST), especialista en la normativa NTC 3701 y en la metodología de los 5 Por Qué.

    Analiza el siguiente evento o condición subestándar reportado en una empresa: "{texto_hallazgo}"

    Tu tarea es realizar una investigación exhaustiva y generar un análisis estructurado. Debes seguir EXACTAMENTE este formato JSON. No agregues texto fuera del JSON.
    Asegúrate de utilizar códigos y terminología real de la NTC 3701 para las causas inmediatas y básicas.

    {{
      "categoria": "Clasificación principal del riesgo (Ej: Riesgo Eléctrico, Mobiliario/Ergonomía, Infraestructura/Locativo, Biológico, Mecánico, etc.)",
      "evento": "Descripción capitalizada y profesional del evento proporcionado",
      "porques": [
        "¿Por qué ocurrió el evento? -> [Respuesta lógica basada en el evento]",
        "¿Por qué sucedió la respuesta anterior? -> [Profundización]",
        "¿Por qué se generó esa situación? -> [Profundización en gestión]",
        "¿Por qué no se detectó o previno? -> [Falla en el sistema de control]",
        "¿Por qué existe esa falla en el sistema? -> [Causa raíz organizacional]"
      ],
      "causa_raiz": "Enunciado claro y conciso de la causa raíz identificada tras el análisis de los 5 Por Qué.",
      "actos_sub": ["Código y nombre real de NTC 3701 de Actos subestándar aplicables (Ej: 550 - Adoptar posición insegura)"],
      "condiciones_sub": ["Código y nombre real de NTC 3701 de Condiciones subestándar aplicables (Ej: 035 - Desgastado, roto; 510 - Riesgo eléctrico)"],
      "factores_personales": ["Código y nombre real de NTC 3701 (Ej: 998 - Ningún factor personal relevante, o el que aplique)"],
      "factores_trabajo": ["Código y nombre real de NTC 3701 (Ej: 300 - Mantenimiento deficiente; 000 - Supervisión deficiente)"],
      "acciones": [
        {{
          "titulo": "Nombre de la acción correctiva o preventiva",
          "objetivo": "Qué se busca lograr con esta acción",
          "actividades": "Paso a paso de la actividad (separado por saltos de línea \\n)",
          "responsable": "Área o rol responsable",
          "frecuencia": "Frecuencia de ejecución (Ej: Inmediata, Mensual, Trimestral)"
        }},
        {{
          "titulo": "Nombre de la segunda acción (preventiva)",
          "objetivo": "Qué se busca lograr",
          "actividades": "Paso a paso",
          "responsable": "Área o rol",
          "frecuencia": "Frecuencia"
        }}
      ],
      "conclusion": "Conclusión técnica profesional que relaciona el evento con la causa raíz y el factor predominante (Organizacional, Humano, Técnico)."
    }}

    Genera SOLO un objeto JSON válido y nada más.
    """

    try:
        chat_completion = client_groq.chat.completions.create(
            messages=[{"role": "user", "content": prompt_ia}],
            model="llama-3.1-8b-instant",
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        text_response = chat_completion.choices[0].message.content.strip()
        analisis = json.loads(text_response)
        
        keys_requeridas = ["categoria", "evento", "porques", "causa_raiz", "actos_sub", "condiciones_sub", "factores_personales", "factores_trabajo", "acciones", "conclusion"]
        for key in keys_requeridas:
            if key not in analisis:
                if key == "acciones":
                    analisis[key] = [{"titulo": "Acción pendiente", "objetivo": "Pendiente", "actividades": "Pendiente", "responsable": "SST", "frecuencia": "Pendiente"}]
                elif isinstance(analisis.get(key), list):
                    analisis[key] = ["Pendiente por IA"]
                else:
                    analisis[key] = "Pendiente por IA"
        return analisis

    except Exception as e:
        return {
            "categoria": "Error de Procesamiento IA",
            "evento": texto_hallazgo.capitalize(),
            "porques": ["No se pudo completar el análisis profundo en este momento."],
            "causa_raiz": f"Error al interpretar la respuesta de la IA: {e}",
            "actos_sub": ["N/A"],
            "condiciones_sub": ["N/A"],
            "factores_personales": ["N/A"],
            "factores_trabajo": ["N/A"],
            "acciones": [{"titulo": "Reintentar", "objetivo": "Generar el análisis nuevamente", "actividades": "Intente de nuevo más tarde", "responsable": "SST", "frecuencia": "Inmediata"}],
            "conclusion": "La IA no pudo procesar la solicitud en formato JSON."
        }

# --- FUNCIONES SUPABASE ---
def save_to_supabase(tipo_input, descripcion, resultado, image_url=None):
    if CLOUD_CONNECTED:
        try:
            data = {
                "tipo_input": tipo_input,
                "descripcion": descripcion,
                "categoria_detectada": resultado.get('categoria', 'N/A'),
                "causa_raiz": resultado.get('causa_raiz', 'N/A'),
                "conclusion": resultado.get('conclusion', 'N/A'),
                "image_url": image_url
            }
            supabase.table('historial_ia').insert(data).execute()
        except Exception as e:
            st.error(f"Error guardando en nube: {e}")

def load_historial_supabase():
    if CLOUD_CONNECTED:
        try:
            response = supabase.table('historial_ia').select("*").execute()
            df = pd.DataFrame(response.data)
            if not df.empty and 'fecha_analisis' in df.columns:
                df['fecha_analisis'] = pd.to_datetime(df['fecha_analisis'])
                df = df.sort_values(by='fecha_analisis', ascending=False)
            return df
        except Exception as e:
            st.error(f"Error leyendo nube: {e}")
    return pd.DataFrame()

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_data = None

init_users_db()

# ==========================================
# PANTALLA DE LOGIN / REGISTRO
# ==========================================
if not st.session_state.authenticated:
    st.title("🛡️ Inteligencia Preventiva SST - Acceso")
    menu_auth = st.selectbox("Selecciona una opción", ["Iniciar Sesión", "Registrarse"])
    current_ip = get_client_ip()

    if menu_auth == "Registrarse":
        with st.form("Registro"):
            st.markdown("### Crear Cuenta (Prueba Gratuita 3 Días)")
            cedula = st.text_input("Número de Cédula")
            nombre = st.text_input("Nombres Completos")
            fecha_nac = st.date_input("Fecha de Nacimiento")
            correo = st.text_input("Correo Electrónico (Será tu usuario)")
            celular = st.text_input("Celular")
            clave = st.text_input("Clave", type="password")
            if st.form_submit_button("Registrarse"):
                if cedula and nombre and correo and clave:
                    success = register_user(cedula, nombre, str(fecha_nac), correo, celular, clave, current_ip)
                    if success: st.success("✅ Registro exitoso. Ya puedes iniciar sesión.")
                    else: st.error("⚠️ Ya se encuentra registrado. Contacte al administrador.")
                else: st.warning("Todos los campos son obligatorios.")
    else:
        correo = st.text_input("Usuario (Correo)")
        clave = st.text_input("Clave", type="password")
        if st.button("Ingresar"):
            if correo and clave:
                user_data, msg = verify_user(correo, clave, current_ip)
                if user_data:
                    st.session_state.authenticated = True
                    st.session_state.user_data = user_data
                    st.rerun()
                else: st.error(msg)
            else: st.warning("Ingresa usuario y clave.")

# ==========================================
# APLICACIÓN PRINCIPAL (LOGUEADO)
# ==========================================
else:
    user = st.session_state.user_data
    is_admin = (user['correo'] == 'dasb1512')
    
    st.sidebar.markdown(f"👤 **{user['nombre']}**")
    if is_admin:
        st.sidebar.markdown("🛡️ Administrador")
    else:
        dias_restantes = 3 - (datetime.now() - datetime.strptime(user['fecha_registro'].split('.')[0], "%Y-%m-%d %H:%M:%S")).days
        st.sidebar.markdown(f"⏳ Días gratis restantes: **{max(0, dias_restantes)}**")
    
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.authenticated = False
        st.session_state.user_data = None
        st.rerun()

    st.sidebar.markdown("---")
    opciones_menu = ["📊 Dashboard KPIs", "🤖 IA Predictiva (5 Por Qué)", "📁 Exportar Datos"]
    if is_admin: opciones_menu.append("👥 Panel de Administración")
    menu = st.sidebar.radio("Navegación", opciones_menu)

    # --- PANEL ADMIN ---
    if menu == "👥 Panel de Administración" and is_admin:
        st.title("👥 Panel de Administración")
        conn = init_users_db()
        df_users = pd.read_sql_query("SELECT cedula, nombre, correo, celular, fecha_registro, aprobado FROM users WHERE correo != 'dasb1512'", conn)
        if not df_users.empty:
            for index, row in df_users.iterrows():
                with st.container():
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        estado = "✅ Aprobado" if row['aprobado'] else "⏳ Trial/Bloqueado"
                        st.write(f"**{row['nombre']}** - {row['correo']} | Estado: {estado}")
                    with col2:
                        if not row['aprobado']:
                            if st.button("Aprobar Acceso", key=row['cedula']):
                                c = conn.cursor()
                                c.execute("UPDATE users SET aprobado=1 WHERE cedula=?", (row['cedula'],))
                                conn.commit()
                                st.success(f"Usuario {row['nombre']} aprobado."); st.rerun()
                    with col3:
                        if row['aprobado']:
                            if st.button("Revocar Acceso", key=f"rev_{row['cedula']}"):
                                c = conn.cursor()
                                c.execute("UPDATE users SET aprobado=0 WHERE cedula=?", (row['cedula'],))
                                conn.commit()
                                st.warning(f"Acceso de {row['nombre']} revocado."); st.rerun()
        else: st.info("No hay usuarios registrados además del administrador.")

    # --- DASHBOARD ---
    elif menu == "📊 Dashboard KPIs":
        st.title("🛡️ De la Gestión a la Inteligencia Preventiva")
        st.markdown("### Indicadores Reales del Ecosistema Integrado")
        
        df_ia = load_historial_supabase()
        total_eventos_ia = len(df_ia)
        
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.markdown('<div class="metric-card"><div class="kpi-value">68% ↓</div><div class="kpi-label">Reducción Tiempo Cierre</div></div>', unsafe_allow_html=True)
        with col2: st.markdown('<div class="metric-card"><div class="kpi-value">75% ↓</div><div class="kpi-label">Reducción Recurrencia</div></div>', unsafe_allow_html=True)
        with col3: st.markdown('<div class="metric-card"><div class="kpi-value">95% ↑</div><div class="kpi-label">Análisis Causa Raíz</div></div>', unsafe_allow_html=True)
        with col4: st.markdown(f'<div class="metric-card"><div class="kpi-value">{total_eventos_ia}</div><div class="kpi-label">Eventos Procesados IA</div></div>', unsafe_allow_html=True)
        
        st.markdown("---")
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            st.subheader("Impacto del Modelo Integrado")
            categorias = ['Tiempo Cierre', 'Recurrencia', 'Causa Raíz']
            fig = go.Figure([go.Bar(name='Antes', x=categorias, y=[28, 32, 12], marker_color='#e74c3c'), go.Bar(name='Después', x=categorias, y=[9, 8, 95], marker_color='#2ecc71')])
            fig.update_layout(barmode='group', template='plotly_white')
            st.plotly_chart(fig, width='stretch')
        with col_chart2:
            st.subheader("Distribución por Factor de Riesgo (IA)")
            if not df_ia.empty:
                cat_counts = df_ia['categoria_detectada'].value_counts().reset_index()
                cat_counts.columns = ['Categoria', 'Cantidad']
                fig2 = px.pie(cat_counts, values='Cantidad', names='Categoria', hole=0.4)
                st.plotly_chart(fig2, width='stretch')
            else: st.info("Sin datos de IA aún.")

        st.markdown("---")
        st.subheader("📸 Últimos Hallazgos con Visión IA")
        if not df_ia.empty and 'image_url' in df_ia.columns:
            df_con_img = df_ia[df_ia['image_url'].notna()].head(3)
            if not df_con_img.empty:
                cols = st.columns(len(df_con_img))
                for idx, (_, row) in enumerate(df_con_img.iterrows()):
                    with cols[idx]:
                        try: st.image(row['image_url'], caption=row['categoria_detectada'])
                        except: st.warning("Error cargando imagen")
            else: st.info("Aún no se han subido imágenes.")
        else: st.info("Aún no hay datos en la nube.")

    # --- IA PREDICTIVA ---
    elif menu == "🤖 IA Predictiva (5 Por Qué)":
        st.title("🤖 Motor de Investigación y Predicción NTC 3701")
        input_type = st.radio("¿Cómo desea ingresar el hallazgo?", ("📝 Escribir Texto", "📷 Subir Imagen (IA Vision)"))
        texto_analizar = ""

        if input_type == "📝 Escribir Texto":
            texto_analizar = st.text_area("Describa el evento o condición subestándar:", height=150, placeholder="Ej: Derrame de químico en el pasillo...")
            if st.button("🧠 Generar Investigación") and texto_analizar:
                if 'resultado_ia' in st.session_state: 
                    del st.session_state.resultado_ia  
                with st.spinner("La IA está analizando el evento y aplicando NTC 3701..."):
                    resultado = predict_sst_analysis(texto_analizar)
                    save_to_supabase("Texto", texto_analizar, resultado)
                    st.session_state.resultado_ia = resultado
                    st.rerun()

        elif input_type == "📷 Subir Imagen (IA Vision)":
            uploaded_file = st.file_uploader("Toma o sube una foto del acto/condición subestándar", type=['png', 'jpg', 'jpeg'])
            if uploaded_file is not None:
                image = Image.open(uploaded_file)
                st.image(image, caption="Imagen Cargada para Análisis", use_column_width=True)
                if st.button("👁️ Analizar Imagen con IA"):
                    if 'resultado_ia' in st.session_state: 
                        del st.session_state.resultado_ia  
                    with st.spinner("La IA está observando la imagen y deduciendo el riesgo..."):
                        texto_analizar = ""
                        try:
                            buffered = io.BytesIO()
                            image.save(buffered, format="JPEG")
                            img_str = base64.b64encode(buffered.getvalue()).decode()
                            
                            prompt_vision = "Eres un experto en Seguridad y Salud en el Trabajo (SST). Observa esta imagen. Describe en 1 oración concisa la condición subestándar que ves (enfócate en: mobiliario, eléctrico, humedad u obstáculo)."
                            
                            chat_completion = client_groq.chat.completions.create(
                                messages=[
                                    {
                                        "role": "user",
                                        "content": [
                                            {"type": "text", "text": prompt_vision},
                                            {
                                                "type": "image_url",
                                                "image_url": {
                                                    "url": f"data:image/jpeg;base64,{img_str}"
                                                }
                                            }
                                        ]
                                    }
                                ],
                                model="llama-3.2-90b-vision-preview",
                            )
                            texto_analizar = chat_completion.choices[0].message.content
                            st.info(f"📝 **La IA de Visión detectó:** {texto_analizar}")
                                            
                        except Exception as e:
                            st.error(f"🔴 ERROR DE VISIÓN: {e}")
                            st.warning("⚠️ La IA de Visión no está disponible. Modo Colaborativo Activado:")
                            st.info("💡 *Tip: Escribe la condición subestándar que observas (Ej: Silla rota, cable expuesto...)*")
                            texto_analizar = st.text_input("Descripción manual del hallazgo:", key="manual_desc")
                        
                        if texto_analizar:
                            with st.spinner("Generando análisis de causa raíz NTC 3701..."):
                                resultado = predict_sst_analysis(texto_analizar)
                                try:
                                    img_bytes = uploaded_file.getvalue()
                                    file_name = f"{uuid.uuid4().hex}.jpg"
                                    supabase.storage.from_("fotos-sst").upload(file_name, img_bytes, {"content-type": "image/jpeg"})
                                    image_url = supabase.storage.from_("fotos-sst").get_public_url(file_name)
                                    
                                    save_to_supabase("Imagen", texto_analizar, resultado, image_url)
                                    st.session_state.resultado_ia = resultado
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error guardando en la nube: {e}")

        # --- RENDERIZADO DE RESULTADOS ---
        if 'resultado_ia' in st.session_state:
            resultado = st.session_state.resultado_ia
            st.markdown("---")
            col_limpiar, col_spacer = st.columns([1, 5])
            with col_limpiar:
                if st.button("🔄 Limpiar Análisis / Nuevo Hallazgo"):
                    del st.session_state.resultado_ia
                    st.rerun()
                    
            st.success("✅ Análisis Generado y Guardado en la Nube!")
            
            st.markdown("## 1. Análisis de causas – Método de los Cinco Por Qué")
            st.markdown(f"**Evento:** {resultado.get('evento', 'N/A')}")
            porques = resultado.get('porques', [])
            for p in porques: 
                if p and p != "Pendiente por IA": st.markdown(f"**{p}**")
            st.error(f"**Causa raíz identificada:** {resultado.get('causa_raiz', 'N/A')}")
            st.markdown("---")
            
            st.markdown("## 2. Causas inmediatas (NTC 3701)")
            col_acto, col_cond = st.columns(2)
            with col_acto:
                st.markdown("🔴 **Actos subestándar**")
                for a in resultado.get('actos_sub', []): st.markdown(f"- {a}")
            with col_cond:
                st.markdown("🟠 **Condiciones subestándar**")
                for c in resultado.get('condiciones_sub', []): st.markdown(f"- {c}")
            st.markdown("---")

            st.markdown("## 3. Causas básicas (NTC 3701)")
            col_fp, col_ft = st.columns(2)
            with col_fp:
                st.markdown("🔵 **Factores personales**")
                for fp in resultado.get('factores_personales', []): st.info(f"📌 {fp}")
            with col_ft:
                st.markdown("🟣 **Factores del trabajo**")
                for ft in resultado.get('factores_trabajo', []): st.warning(f"⚠️ {ft}")
            st.markdown("---")

            st.markdown("## 4. Plan de acción")
            for i, acc in enumerate(resultado.get('acciones', [])):
                with st.expander(f"✅ Acción {i+1}: {acc.get('titulo', 'Acción')}"):
                    col_obj, col_freq = st.columns(2)
                    col_obj.markdown(f"**Objetivo**\n\n{acc.get('objetivo', 'N/A')}")
                    col_freq.markdown(f"**Frecuencia:** {acc.get('frecuencia', 'N/A')}\n\n**Responsable:** {acc.get('responsable', 'N/A')}")
                    st.markdown(f"**Actividades**\n\n{acc.get('actividades', 'N/A')}")
            st.markdown("---")

            st.markdown("## 5. Conclusión técnica")
            st.success(f"✔️ {resultado.get('conclusion', 'N/A')}")

    # --- EXPORTAR DATOS ---
    elif menu == "📁 Exportar Datos":
        st.title("📥 Exportación de Información Estratégica")
        df_ia = load_historial_supabase()
        st.markdown("### Historial de Predicciones de IA (Nube)")
        st.dataframe(df_ia)
        
        if not df_ia.empty:
            def to_excel(df):
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer: df.to_excel(writer, index=False, sheet_name='Historial_IA_Nube')
                return output.getvalue()
            st.download_button(label="📊 Descargar Excel Historial IA", data=to_excel(df_ia), file_name="Historial_IA_SST.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
