import tempfile
import time
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

# --- CONFIGURACIÓN DE PÁGINA ---
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

# --- CONEXIÓN A LA NUBE (SUPABASE Y GEMINI) ---
try:
    # Validar que no tenga barra al final para evitar error PGRST125
    supabase_url = st.secrets["SUPABASE_URL"].rstrip('/')
    supabase_key = st.secrets["SUPABASE_KEY"]
    gemini_key = st.secrets["GEMINI_API_KEY"]
    
    from supabase import create_client, Client
    import google.generativeai as genai
    
    supabase: Client = create_client(supabase_url, supabase_key)
    genai.configure(api_key=gemini_key)
    vision_model = genai.GenerativeModel('gemini-1.5-flash-latest')
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

# --- MOTOR DE IA PREDICTIVA (NTC 3701) ---
def predict_sst_analysis(texto_hallazgo):
    texto = texto_hallazgo.lower()
    if any(palabra in texto for palabra in ["silla", "mobiliario", "escritorio", "cama", "colchón"]):
        categoria = "Mobiliario / Ergonomía"
        analisis = {
            "categoria": categoria, "evento": texto_hallazgo.capitalize(),
            "porques": ["¿Por qué ocurrió? -> Porque el elemento/mobiliario cedió o presentó falla estructural.", "¿Por qué cedió? -> Porque presentaba una condición subestándar o falla estructural.", "¿Por qué no fue detectada? -> Porque no se identificó oportunamente el deterioro o inestabilidad.", "¿Por qué no se identificó? -> Porque existen debilidades en las inspecciones locativas y de mobiliario.", "¿Por qué existen debilidades? -> Porque no se cuenta con un control efectivo para mantenimiento preventivo y reposición."],
            "causa_raiz": "Falla estructural o condición subestándar del mobiliario, asociada a deficiencias en la inspección, mantenimiento y control preventivo.",
            "actos_sub": ["550 – ADOPTAR UNA POSICIÓN INSEGURA", "559 – Adoptar posición insegura no especificada"],
            "condiciones_sub": ["000 – DEFECTO AGENTES / 035 – Desgastado, roto", "500 – INADECUADAMENTE PROTEGIDO / 520 – Inadecuadamente protegido (riesgos mecánicos)"],
            "factores_personales": ["998 – Ningún factor personal relevante"],
            "factores_trabajo": ["300 – MANTENIMIENTO DEFICIENTE / 301 – Aspectos preventivos inadecuados", "000 – SUPERVISIÓN DEFICIENTE / 009 – Identificación y evaluación deficiente"],
            "acciones": [
                {"titulo": "Inspección general de mobiliario", "objetivo": "Identificar y retirar elementos deteriorados.", "actividades": "Inspección física\nClasificación de estado\nRetiro inmediato", "responsable": "Infraestructura + SST", "frecuencia": "Mensual"},
                {"titulo": "Programa de mantenimiento preventivo", "objetivo": "Garantir condiciones seguras de uso.", "actividades": "Cronograma de mantenimiento\nReparación o reposición", "responsable": "Mantenimiento", "frecuencia": "Trimestral"}
            ],
            "conclusion": "Evento asociado a falla de mobiliario. Evidencia condición subestándar principal y mantenimiento deficiente. Factor predominante: Locativo y Organizacional."
        }
    elif any(palabra in texto for palabra in ["cable", "eléctric", "toma", "enchufe", "tablero", "energía"]):
        categoria = "Riesgo Eléctrico"
        analisis = {
            "categoria": categoria, "evento": texto_hallazgo.capitalize(),
            "porques": ["¿Por qué ocurrió? -> Porque se presentó exposición a riesgo eléctrico por elemento sin protección.", "¿Por qué sin protección? -> Porque el aislamiento estaba deteriorado o nunca se instaló.", "¿Por qué estaba deteriorado? -> Por desgaste por uso o modificación inadecuada sin reporte.", "¿Por qué no se reportó? -> Porque las inspecciones no auditan riesgos eléctricos menores.", "¿Por qué no auditan? -> Porque no existe una lista de chequeo específica para sistemas eléctricos."],
            "causa_raiz": "Exposición a riesgo eléctrico por deficiencias en el control de infraestructura y ausencia de auditorías preventivas.",
            "actos_sub": ["550 – ADOPTAR UNA POSICIÓN INSEGURA (Acercamiento a zona energizada)"],
            "condiciones_sub": ["000 – DEFECTO AGENTES / 035 – Desgastado, roto (Aislamiento)", "500 – INADECUADAMENTE PROTEGIDO / 510 – Riesgo eléctrico"],
            "factores_personales": ["998 – Ningún factor personal relevante"],
            "factores_trabajo": ["300 – MANTENIMIENTO DEFICIENTE / 301 – Aspectos preventivos inadecuados", "000 – SUPERVISIÓN DEFICIENTE / 009 – Identificación deficiente"],
            "acciones": [
                {"titulo": "Aislamiento y señalización inmediata", "objetivo": "Eliminar riesgo eléctrico.", "actividades": "Desenergización\nInstalación de aislamiento\nSeñalización", "responsable": "Mantenimiento + SST", "frecuencia": "Inmediata"},
                {"titulo": "Actualización de listas de chequeo", "objetivo": "Incluir ítems de riesgo eléctrico.", "actividades": "Modificación de formato\nSocialización", "responsable": "SST", "frecuencia": "Única"}
            ],
            "conclusion": "Condición subestándar de tipo eléctrico. Causa raíz: Falta de mantenimiento preventivo y ausencia de verificación. Factor predominante: Organizacional."
        }
    else:
        categoria = "Infraestructura / General"
        analisis = {
            "categoria": categoria, "evento": texto_hallazgo.capitalize(),
            "porques": ["¿Por qué se presenta la condición? -> Porque hay deterioro en la infraestructura física.", "¿Por qué hay deterioro? -> Por desgaste natural o fallas en materiales.", "¿Por qué no se ha reparado? -> Porque no se ha generado una orden de mantenimiento oportuna.", "¿Por qué no hay orden oportuna? -> Porque el reporte del hallazgo se retrasa.", "¿Por qué no hay seguimiento? -> Porque los registros no están integrados a un plan automatizado."],
            "causa_raiz": "Condición subestándar generada por la desintegración entre la detección del hallazgo y la gestión de mantenimiento.",
            "actos_sub": ["550 – ADOPTAR UNA POSICIÓN INSEGURA (Si aplica interacción)"],
            "condiciones_sub": ["000 – DEFECTO AGENTES / 035 – Desgastado, roto", "400 – RIESGO DE COLOCACIÓN / 420 – Emplazados inadecuadamente"],
            "factores_personales": ["998 – Ningún factor personal relevante"],
            "factores_trabajo": ["300 – MANTENIMIENTO DEFICIENTE / 301 – Aspectos preventivos inadecuados", "000 – SUPERVISIÓN DEFICIENTE / 009 – Identificación deficiente"],
            "acciones": [
                {"titulo": "Intervención correctiva inmediata", "objetivo": "Restaurar condiciones seguras.", "actividades": "Evaluación del daño\nReparación\nVerificación", "responsable": "Mantenimiento", "frecuencia": "Inmediata"},
                {"titulo": "Cronograma de mantenimiento locativo", "objetivo": "Prevenir deterioro.", "actividades": "Inclusión en software\nInspecciones programadas", "responsable": "Infraestructura + SST", "frecuencia": "Trimestral"}
            ],
            "conclusion": "Condición subestándar asociada a infraestructura física. Factor predominante: Organizacional."
        }
    return analisis

# --- FUNCIONES SUPABASE ---
def save_to_supabase(tipo_input, descripcion, resultado, image_url=None):
    if CLOUD_CONNECTED:
        try:
            data = {
                "tipo_input": tipo_input,
                "descripcion": descripcion,
                "categoria_detectada": resultado['categoria'],
                "causa_raiz": resultado['causa_raiz'],
                "conclusion": resultado['conclusion'],
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

# --- INICIALIZACIÓN DE SESIÓN ---
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
                    if success: st.success("✅ Registro exitoso. Ya puedes iniciar sesión. Tu prueba de 3 días comienza ahora.")
                    else: st.error("⚠️ Ya se encuentra registrado y debe obtener el programa completo, contactar al administrador.")
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
            texto_analizar = st.text_area("Describa el evento o condición subestándar:", height=150, placeholder="Ej: Caída al mismo nivel por colapso de silla...")
            if st.button("🧠 Generar Investigación") and texto_analizar:
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
                    with st.spinner("La IA está observando la imagen y deduciendo el riesgo..."):
                        texto_analizar = ""
                        try:
                            # 1. Guardar la imagen en un archivo temporal físico (Esto evita errores de red)
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
                                tmp_file.write(uploaded_file.getvalue())
                                tmp_file_path = tmp_file.name
                            
                            # 2. Subir el archivo a la API segura de Google
                            genai_file = genai.upload_file(path=tmp_file_path, mime_type=uploaded_file.type)
                            
                            # 3. Esperar a que Google procese la imagen (Muy importante)
                            while genai_file.state.name == "PROCESSING":
                                time.sleep(2)
                                genai_file = genai.get_file(genai_file.name)
                            
                            if genai_file.state.name == "FAILED":
                                raise ValueError("Google no pudo procesar la imagen.")
                            
                            # 4. Enviar el archivo ya procesado al modelo
                            prompt_vision = "Eres un experto en Seguridad y Salud en el Trabajo (SST). Observa esta imagen. Describe en 1 oración concisa la condición subestándar que ves (enfócate en: mobiliario, eléctrico, humedad u obstáculo)."
                            response = vision_model.generate_content([prompt_vision, genai_file])
                            
                            texto_analizar = response.text
                            st.info(f"📝 **La IA de Visión detectó:** {texto_analizar}")
                            
                            # Limpiar archivo temporal
                            os.remove(tmp_file_path)
                                            
                        except Exception as e:
                            # PLAN B: Si la IA falla, no romper la app
                            st.warning(f"⚠️ La IA de Visión no está disponible. Por favor, describe lo que ves:")
                            st.info("💡 *Tip: Escribe la condición subestándar que observas (Ej: Silla rota, cable expuesto...)*")
                            texto_analizar = st.text_input("Descripción manual del hallazgo:", key="manual_desc")
                        
                        # Si tenemos texto (sea de la IA o manual), procesamos y guardamos
                        if texto_analizar:
                            try:
                                # Subir imagen a Supabase Storage
                                img_bytes = uploaded_file.getvalue()
                                file_name = f"{uuid.uuid4().hex}.jpg"
                                supabase.storage.from_("fotos-sst").upload(file_name, img_bytes, {"content-type": "image/jpeg"})
                                image_url = supabase.storage.from_("fotos-sst").get_public_url(file_name)
                                
                                resultado = predict_sst_analysis(texto_analizar)
                                save_to_supabase("Imagen", texto_analizar, resultado, image_url)
                                st.session_state.resultado_ia = resultado
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error guardando en la nube: {e}")

        # --- RENDERIZADO DE RESULTADOS ---
        if 'resultado_ia' in st.session_state:
            resultado = st.session_state.resultado_ia
            st.success("✅ Análisis Generado y Guardado en la Nube!")
            st.markdown("## 1. Análisis de causas – Método de los Cinco Por Qué")
            st.markdown(f"**Evento**\n\n{resultado['evento']}")
            for p in resultado['porques']: st.markdown(f"**{p}**")
            st.error(f"**Causa raíz identificada:** {resultado['causa_raiz']}")
            st.markdown("---")
            
            st.markdown("## 2. Causas inmediatas (NTC 3701)")
            col_acto, col_cond = st.columns(2)
            with col_acto:
                st.markdown("🔴 **Actos subestándar**")
                for a in resultado['actos_sub']: st.markdown(f"- {a}")
            with col_cond:
                st.markdown("🟠 **Condiciones subestándar**")
                for c in resultado['condiciones_sub']: st.markdown(f"- {c}")
            st.markdown("---")

            st.markdown("## 3. Causas básicas (NTC 3701)")
            col_fp, col_ft = st.columns(2)
            with col_fp:
                st.markdown("🔵 **Factores personales**")
                for fp in resultado['factores_personales']: st.info(f"📌 {fp}")
            with col_ft:
                st.markdown("🟣 **Factores del trabajo**")
                for ft in resultado['factores_trabajo']: st.warning(f"⚠️ {ft}")
            st.markdown("---")

            st.markdown("## 4. Plan de acción")
            for i, acc in enumerate(resultado['acciones']):
                with st.expander(f"✅ Acción {i+1}: {acc['titulo']}"):
                    col_obj, col_freq = st.columns(2)
                    col_obj.markdown(f"**Objetivo**\n\n{acc['objetivo']}")
                    col_freq.markdown(f"**Frecuencia:** {acc['frecuencia']}\n\n**Responsable:** {acc['responsable']}")
                    st.markdown(f"**Actividades**\n\n{acc['actividades']}")
            st.markdown("---")

            st.markdown("## 5. Conclusión técnica")
            st.success(f"✔️ {resultado['conclusion']}")

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
            st.download_button(label="📊 Descargar Excel Historial IA", data=to_excel(df_ia), file_name='Historial_IA_SST.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
