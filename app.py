import streamlit as st
import google.generativeai as genai
import time
import re
import os
import mimetypes
import tempfile
import speech_recognition as sr
import hashlib
from PyPDF2 import PdfReader
from docx import Document
import pytesseract
from PIL import Image
import pandas as pd
import json
import xml.etree.ElementTree as ET
from io import BytesIO
import base64
from datetime import datetime, timedelta

# Check for password in session state and persistent login

def initialize_font_preferences():
    if 'font_preferences' not in st.session_state:
        # Try to load from local storage
        placeholder_div = st.empty()
        placeholder_div.markdown(
            """
            <div id="load_font_preferences" style="display:none;"></div>
            <script>
                const prefDiv = document.getElementById('load_font_preferences');
                const savedPrefs = localStorage.getItem('onco_aide_font');
                if (savedPrefs) {
                    prefDiv.innerText = savedPrefs;
                } else {
                    prefDiv.innerText = JSON.stringify({
                        font_family: "Montserrat",
                        text_size: "medium"
                    });
                }
                setTimeout(() => {
                    window.parent.postMessage({
                        type: 'streamlit:setComponentValue',
                        value: prefDiv.innerText,
                        dataType: 'string',
                        key: 'loaded_font_preferences'
                    }, '*');
                }, 100);
            </script>
            """,
            unsafe_allow_html=True
        )
        
        # Wait for the JavaScript to set the value
        if 'loaded_font_preferences' in st.session_state:
            placeholder_div.empty()
            try:
                st.session_state.font_preferences = json.loads(st.session_state.loaded_font_preferences)
            except:
                # Default preferences if loading fails
                st.session_state.font_preferences = {
                    "font_family": "Montserrat",
                    "text_size": "medium"
                }
        else:
            # Default preferences
            st.session_state.font_preferences = {
                "font_family": "Montserrat",
                "text_size": "medium"
            }

def save_font_preferences():
    prefs_json = json.dumps(st.session_state.font_preferences)
    st.markdown(
        f"""
        <script>
            localStorage.setItem('onco_aide_font', '{prefs_json}');
        </script>
        """,
        unsafe_allow_html=True
    )

def apply_font_preferences():
    font_family = st.session_state.font_preferences.get("font_family", "Montserrat")
    text_size = st.session_state.font_preferences.get("text_size", "medium")
    
    # Map text size names to actual CSS values
    size_map = {
        "small": "0.9rem",
        "medium": "1rem",
        "large": "1.2rem",
        "x-large": "1.4rem"
    }
    
    font_size = size_map[text_size]
    
    # Apply CSS based on preferences
    st.markdown(f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family={font_family.replace(' ', '+')}:wght@300;400;500;600;700&display=swap');
        
        * {{
            font-family: '{font_family}', sans-serif !important;
            font-size: {font_size} !important;
        }}
        
        .stMarkdown, .stText, .stTitle, .stHeader {{
            font-family: '{font_family}', sans-serif !important;
        }}
        
        .stButton button {{
            font-family: '{font_family}', sans-serif !important;
        }}
        
        .stTextInput input {{
            font-family: '{font_family}', sans-serif !important;
        }}
        
        .stSelectbox select {{
            font-family: '{font_family}', sans-serif !important;
        }}
        
        /* Adjust heading sizes proportionally */
        h1 {{
            font-size: calc({font_size} * 2.0) !important;
        }}
        
        h2 {{
            font-size: calc({font_size} * 1.5) !important;
        }}
        
        h3 {{
            font-size: calc({font_size} * 1.3) !important;
        }}
    </style>
    """, unsafe_allow_html=True)


def initialize_custom_commands():
    if 'custom_commands' not in st.session_state:
        # Try to load from local storage
        placeholder_div = st.empty()
        placeholder_div.markdown(
            """
            <div id="load_commands" style="display:none;"></div>
            <script>
                const cmdDiv = document.getElementById('load_commands');
                const savedCmds = localStorage.getItem('onco_aide_custom_commands');
                if (savedCmds) {
                    cmdDiv.innerText = savedCmds;
                } else {
                    cmdDiv.innerText = JSON.stringify({});
                }
                setTimeout(() => {
                    window.parent.postMessage({
                        type: 'streamlit:setComponentValue',
                        value: cmdDiv.innerText,
                        dataType: 'string',
                        key: 'loaded_commands'
                    }, '*');
                }, 100);
            </script>
            """,
            unsafe_allow_html=True
        )
        
        # Wait for the JavaScript to set the value
        if 'loaded_commands' in st.session_state:
            placeholder_div.empty()
            try:
                st.session_state.custom_commands = json.loads(st.session_state.loaded_commands)
            except:
                st.session_state.custom_commands = {}
        else:
            st.session_state.custom_commands = {}

def save_custom_commands():
    cmds_json = json.dumps(st.session_state.custom_commands)
    st.markdown(
        f"""
        <script>
            localStorage.setItem('onco_aide_custom_commands', '{cmds_json}');
        </script>
        """,
        unsafe_allow_html=True
    )

# Initialize Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("Missing GEMINI_API_KEY environment variable")

genai.configure(api_key=GEMINI_API_KEY)

# Page configuration
st.set_page_config(
    page_title="ESL at Home - AI Chatbot",
    page_icon="./favicon.ico",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>

    .stChatInputContainer {
        display: flex;
        align-items: center;
    }
</style>
<script>
document.addEventListener('paste', function(e) {
    if (document.activeElement.tagName !== 'TEXTAREA' && document.activeElement.tagName !== 'INPUT') {
        e.preventDefault();
        const items = e.clipboardData.items;
        
        for (const item of items) {
            if (item.type.indexOf('image') !== -1) {
                const blob = item.getAsFile();
                const reader = new FileReader();
                reader.onload = function(e) {
                    const base64data = e.target.result;
                    window.parent.postMessage({
                        type: 'clipboard_paste',
                        data: base64data,
                        format: 'image'
                    }, '*');
                };
                reader.readAsDataURL(blob);
            } else if (item.type === 'text/plain') {
                item.getAsString(function(text) {
                    window.parent.postMessage({
                        type: 'clipboard_paste',
                        data: text,
                        format: 'text'
                    }, '*');
                });
            }
        }
    }
});
window.addEventListener('message', function(e) {
    if (e.data.type === 'clipboard_paste') {
        const args = {
            'data': e.data.data,
            'format': e.data.format
        };
        window.parent.postMessage({
            type: 'streamlit:set_widget_value',
            key: 'clipboard_data',
            value: args
        }, '*');
    }
});
</script>""", unsafe_allow_html=True)

generation_config = {
    "temperature": 0,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

SYSTEM_INSTRUCTION = """
Name: Your name is OncoAIDE. Your name stands for OncoAI Dialogue Engine

Behavioral Guidelines:
Be helpful and professional, ensuring accuracy in every response.
Maintain a friendly, approachable tone while providing precise and concise answers.
Keep all discussions focused around cancer studies.
Always make sure to keep the discussion focused around cancer and studying it or OncoAI.
After every message, put a new line and type out Citations: in bold, and provide any relevant links online to helpful sources as a citation of sorts.

INFORMATION ABOUT ONCOAIDE:
OncoAIDE stands for OncoAI Dialogue Engine is an AI chatbot companion to OncoAI, a free, universally-accessible diagnostic cancer tool at https://oncoai.org/.
OncoAI can screen for (1) Brain Cancer, (2) Pancreatic Cancer, (3) Lung Colon, (4) Colon Cancer, (5) Breast Cancer, (6) Gastrointestinal Cancer, (7) Cervical Cancer, (8) Skin Cancer, (9) Osteosarcoma/Bone Cancer, and (1) Fundus Neoplasm/Ocular Neoplasm.
One can upload a SINGLE image for a detailed view of the breakdown of their cancer prediction or upload multiple for a quick show of results.
An overall summary of predictions is provided showing the total images upload, time taken for full screening, and breakdown of categories.

INFORMATION ABOUT THE CANCERS ONCOAI SCREENS FOR:
(1) Brain Cancer - Imaging Type: MRI (Radiology), Categories/Screening Capabilities: Glioma, Meningioma, No Tumor, Pituitary Tumor - Significance: Multicancer Detection - Datastes: SARTAJ, Br35h
(2) Pancreatic Cancer - Imaging Type: CT (Radiology), Categories/Screening Capabilities: Normal, Malignant - Significance: Close to 100% Accuracy, >99% - Dataset: Kaggle Dataset (https://www.kaggle.com/datasets/jayaprakashpondy/pancreatic-ct-images)
(3) Lung Cancer - Imaging Type: CT (Radiology), Categories/Screening Capabilities: Benign, Malignant - Significance: Less Amount of Data, High (>95%) Accuracy - Dataset: IQ-OTH/NCCD
(4) Colon Cancer - Imaging Type: H&E-Stained Slides (Histopathological Examinations), Categories/Screening Capabilities: Benign, Malignant - Significance: Large Amount of Images, High (>99) Accuracy - Dataset: LC25000
(5) Breast Cancer - Imaging Type: H&E-Stained Slides (Histopathological Examinations), Categories/Screening Capabilities: Benign, Malignant - Significance: Multimodal Imaging (Also works with Breast Mammogram/Radiology data) - Dataset: BreakHis (Mammogram: INbreast, MIAS, DDSM)
(6) Gastrointestinal Cancer - Imaging Type: H&E-Stained Slides (Histopathological Examinations), Categories/Screening Capabilities: Microsatellite Stable, Microsatellite Instability Mutated - Significance: Uses genomics-related information with mutations - Dataset: Kaggle Dataset (https://www.kaggle.com/datasets/linjustin/train-val-test-tcga-coad-msi-mss)
(7) Cervical Cancer - Imaging Type: Pap Smear (Cytology/HPE), Categories/Screening Capabilities: Dyskeratotic, Koilocytotic, Metaplastic, Parabasal, Superficial Intermediate - Significance: More cellular origins and multicancer differentiation - Dataset: SIPaKMeD
(8) Skin Cancer - Imaging Type: Photography, Categories/Screening Capabilities: Benign, Malignant - Signficance: Uses simple photography to diagnose - Dataset: ISIC Archive
(9) Osteosarcoma - Imaging Type: H&E-Stained Slides (Histopathological Examinations), Categories/Screening Capabilities: Non-Tumor, Non-Viable, Viable - Significance: Tests Therapy Response & Viability with >99% Accuracy - Dataset: Kaggle Dataset (https://www.kaggle.com/datasets/gauravupadhyay0312/osteosarcoma)
(10) Fundus Neoplasm - Imaging Type: Funduscopy, Categories/Screening Capabilities: Normal, Neoplasm - Significance: Tests in Funduscopic Images - Dataset: JSIEC

DATASET INFORMATION:
ISIC Archive [~3000 images] - International Data - Kaggle (https://www.kaggle.com/datasets/fanconic/skin-cancer-malignant-vs-benign), Nature Paper (https://www.nature.com/articles/s41597-021-00815-z)
SARTAJ - India, Br35h - Egypt [SARTAJ + Br35h ~7000 images] - Kaggle (https://www.kaggle.com/datasets/masoudnickparvar/brain-tumor-mri-dataset), Nature Paper (https://www.nature.com/articles/s41598-025-85874-7)
BreakHis [~1800 images] - Brazil - Kaggle (https://www.kaggle.com/datasets/forderation/breakhis-400x), Nature Paper (https://www.nature.com/articles/s41598-017-04075-z)
INbreast - Portugal, MIAS - UK, DDSM - USA [~50000 images] - Kaggle (https://www.kaggle.com/datasets/tommyngx/breastcancermasses/data), Nature Paper (https://www.nature.com/articles/s41597-023-02430-6)
IQ-OTH/NCCD [~1300 images] - Iraq - Kaggle (https://www.kaggle.com/datasets/adityamahimkar/iqothnccd-lung-cancer-dataset), ResearchGate Publication (https://www.researchgate.net/publication/348163312_Evaluation_of_SVM_Performance_in_the_Detection_of_Lung_Cancer_in_Marked_CT_Scan_Dataset)
LC25000 [25000 images] - USA - Kaggle (https://www.kaggle.com/datasets/andrewmvd/lung-and-colon-cancer-histopathological-images), Nature Paper (https://www.nature.com/articles/s41598-025-86362-8)
Osteosarcoma [~1000 images] - Kaggle (https://www.kaggle.com/datasets/gauravupadhyay0312/osteosarcoma), Nature Paper (https://www.nature.com/articles/s41698-024-00515-y)
JSIEC [1000 images] - China - Kaggle (https://www.kaggle.com/datasets/linchundan/fundusimage1000), Nature Paper (https://www.nature.com/articles/s41586-023-06555-x)
SIPaKMeD [~21000 images] - Greece - Kaggle (https://www.kaggle.com/datasets/prahladmehandiratta/cervical-cancer-largest-dataset-sipakmed), Nature Paper (https://www.nature.com/articles/s41597-024-03596-3)
Pancreatic [~1500 images] - Kaggle (https://www.kaggle.com/datasets/jayaprakashpondy/pancreatic-ct-images), Nature Paper (https://www.nature.com/articles/s41591-023-02332-5)
Gastrointestinal [~200000 images] - Kaggle (https://www.kaggle.com/datasets/joangibert/tcga_coad_msi_mss_jpg), Zenodo Record (https://zenodo.org/records/2530835#.XVPlRHUzYeM)

Total: ~310000 images

-- MORE INFORMATION --
OncoAI solves the problem of the global cancer crisis and how diagnostic challenges lead to healthcare inequities. The need is early detection, accurate diagnosis, and universal applicability of such a tool. OncoAI was the solution as an AI-powered application for multimodal imaging.
The constraints of OncoAI are possible data biases, ethical concerns, or infrastructure limitations.

For the study in which OncoAI was built, the hypothesis was 'Efficient AI-powered deep learning models integrated into a multi-platform application can achieve unparalleled accuracy, precision and scalability in diagnosing and classifying diverse cancers globally.'
The aim was 'to develop a universal, AI-driven application for early detection, accurate classification and therapy response evaluation of multiple cancers across diverse imaging modalities and populations worldwide.'
The objectives were (1) to evaluate deep learning architectures on multimodal cancer imaging for precise tumor detection and classification, (2) to integrate efficient AI models into a scalable, crossplatform application for improved computational performance, and (3) to provide a universally-accessible affordable diagnostic solution promote and enhance equitable healthcare.

The training data was split into 60% training, 20% validation, 20% testing for all the individual cancers.
The steps in creating the OncoAI application involved (1) exporting PTH models from the Python code, (2) using HuggingFace Large File Storage (LFS) to create publicly-available APIs for the PTH models, (3) programming the application through GitHub, (4) hosting the application on web through Streamlit Community Cloud and (5) validating the application through experts worldwide.

The methodology of the product had three phases.
Phase 1 was evaluating 7 AI models (EfficientNet B0 & B1, ResNet 18, 34, 50, 101, 152 - all the ResNets) for accuracy, loss, precision, recall, F1 and F2 scores over 30 epochs to see which is the best for accuracy in classifying medical images. EfficientNetB0 and ResNet18 were the most optimal.
Phase 2 was evaluating EfficientNetB0 and ResNet18 in different clinical conditions (normal vs. malignant, benign vs. malignant, different types of imaging, more than two categories, cancers of different cellular origins, multiple cancers, microsatellite instabilities, data from different places in the world, and tumor viability).
Phase 3 was developing the OncoAI application.

The accuracy of EfficientNetB0 in classifying fundus neoplasm was 99% for the 'Normal' category and 100% for the 'Malignant' category.
The accuracy of ResNet18 in classifying fundus neoplasm was 97% for the 'Normal' category and 98% for the 'Malignant' category.
The accuracy of EfficientNetB0 in classifying breast tumors using histopathological examinations was 100% for the 'Benign' category and 100% for the 'Malignant' category.
The accuracy of ResNet18 in classifying breast tumors using histopathological examinations was 99% for the 'Benign' category and 99% for the 'Malignant' category.
The accuracy of EfficientNetB0 in classifying pancreatic tumors was 100% for the 'Normal' category and 100% for the 'Malignant' category.
The accuracy of ResNet18 in classifying pancreatic tumors was 98% for the 'Normal' category and 97% for the 'Malignant' category.
The accuracy of EfficientNetB0 in classifying skin lesions was 100% for the 'Benign' category and 99% for the 'Malignant' category.
The accuracy of ResNet18 in classifying skin lesions was 95% for the 'Benign' category and 95% for the 'Malignant' category.
The accuracy of EfficientNetB0 in classifying colon tumors was 100% for the 'Benign' category and 100% for the 'Malignant' category.
The accuracy of ResNet18 in classifying colon tumors was 99% for the 'Benign' category and 99% for the 'Malignant' category.
The accuracy of EfficientNetB0 in classifying lung tumors was 93% for the 'Benign' category and 94% for the 'Malignant' category.
The accuracy of ResNet18 in classifying lung tumors was 90% for the 'Benign' category and 91% for the 'Malignant' category.
The accuracy of EfficientNetB0 in classifying cervical tumors was 100% for the 'Dyskeratotic' category, 99% for the 'Koilocytotic' category, 100% for the 'Metaplastic' category, 100% for the 'Parabasal' category and 100% for the 'Superficial Intermediate' category.
The accuracy of ResNet18 in classifying cervical tumors was 98% for the 'Dyskeratotic' category, 98% for the 'Koilocytotic' category, 99% for the 'Metaplastic' category, 100% for the 'Parabasal' category and 98% for the 'Superficial Intermediate' category.
The accuracy of EfficientNetB0 in classifying gastrointestinal tumors was 99% for the 'Microsatellite Stable (MSS)' category and 99% for the 'Microsatellite Instability Mutated (MSIMUT)' category.
The accuracy of ResNet18 in classifying gastrointestinal tumors was 98% for the 'Microsatellite Stable (MSS)' category and 97% for the 'Microsatellite Instability Mutated (MSIMUT)' category.
The accuracy of EfficientNetB0 in classifying brain tumors was 100% for the 'Glioma' category, 100% for the 'Meningioma' category, 100% for the 'No Tumor' category and 100% for the 'Pituitary Tumor' category.
The accuracy of ResNet18 in classifying brain tumors was 99% for the 'Glioma' category, 100% for the 'Meningioma' category, 100% for the 'No Tumor' category and 99% for the 'Pituitary Tumor' category.
The accuracy of EfficientNetB0 in classifying bone tumors was 99% for the 'Non-Tumor' category, 99% for the 'Non-Viable' category and 100% for the 'Viable Tumor' category.
The accuracy of ResNet18 in classifying bone tumors was 99% for the 'Non-Tumor' category, 99% for the 'Non-Viable' category and 99% for the 'Viable Tumor' category.

When tested for computational efficiency in terms of diagnosis speed, EfficientNetB0 was able to perform 40 seconds faster than ResNet18 for 1000 images at a single time.
The OncoAI app is currently being validated by 30 physicians across the globe for accuracy in medical data.

The significance of OncoAI for cancer patients is (1) free, available cancer screening, (2) an easy, reliable source of cancer education through OncoAIDE, (3) healthcare privacy since all diagnoses and images provided are private, and (4) personalized care as you control your medical decisions.
The significance of OncoAI for healthcare providers is (1) accurate diagnoses, (2) predictions to aid in prognosis, (3) effective triaging, and (4) expert consultation as a second opinion in medical decisions.
The significance of OncoAI for biomedical scientists is (1) anonymized data for use in new scientific studies, (2) multimodal data for enhanced research capabilities, and (3) predictive analysis for use in other studies.
The significance of OncoAI for cancer specialists is (1) a system for easy collaboration to improve efficiency, (2) effective triaging, and (3) precision care.

Current works in progress for OncoAI is new cancers being added for screening, developing wearable AI-integrated devices for point-of-care diagnostics, and collaborating with physicians worldwide to confirm the validity of OncoAI in real-world settings.
The future directions for OncoAI include prospective clinical trials to ensure accuracy and regulatory approval for clinical deployment.

If someone asks about preventing cancer and it is relatd to one of the cancers, mention OncoAI as a way for early detection and rapid treatment.
"""
    
def initialize_session_state():
    
    if 'chat_model' not in st.session_state:
        st.session_state.chat_model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config=generation_config,
            system_instruction=SYSTEM_INSTRUCTION,
        )

    if 'chat_session' not in st.session_state:
        st.session_state.chat_session = st.session_state.chat_model.start_chat(history=[])

    if 'messages' not in st.session_state:
        initial_message = """Welcome to the OncoAI Dialogue Engine. What would you like to learn about?"""
        st.session_state.messages = [
            {"role": "assistant", "content": initial_message}
        ]
    
    if 'uploaded_files' not in st.session_state:
        st.session_state.uploaded_files = []
        
    if 'processed_audio_hashes' not in st.session_state:
        st.session_state.processed_audio_hashes = set()
        
    if 'camera_image' not in st.session_state:
        st.session_state.camera_image = None
        
    if 'camera_enabled' not in st.session_state:
        st.session_state.camera_enabled = False

    if 'clipboard_data' not in st.session_state:
        st.session_state.clipboard_data = None
        
    if 'file_upload_expanded' not in st.session_state:
        st.session_state.file_upload_expanded = False
    initialize_custom_commands()
    
    # For custom command form
    if 'show_custom_cmd_form' not in st.session_state:
        st.session_state.show_custom_cmd_form = False

def get_audio_hash(audio_data):
    return hashlib.md5(audio_data.getvalue()).hexdigest()

def convert_audio_to_text(audio_file):
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(audio_file) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data)
            return text
    except sr.UnknownValueError:
        raise Exception("Speech recognition could not understand the audio")
    except sr.RequestError as e:
        raise Exception(f"Could not request results from speech recognition service; {str(e)}")

def save_audio_file(audio_data):
    audio_bytes = audio_data.getvalue()
    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmpfile:
        tmpfile.write(audio_bytes)
        return tmpfile.name

def process_response(text):
    lines = text.split('\n')
    processed_lines = []
    
    for line in lines:
        if re.match(r'^\d+\.', line.strip()):
            processed_lines.append('\n' + line.strip())
        elif line.strip().startswith('*') or line.strip().startswith('-'):
            processed_lines.append('\n' + line.strip())
        else:
            processed_lines.append(line)
    
    text = '\n'.join(processed_lines)
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    text = re.sub(r'(\n[*-] .+?)(\n[^*\n-])', r'\1\n\2', text)
    
    return text.strip()

def handle_chat_response(response, message_placeholder, command_message=""):
    full_response = ""
    
    # First display command message if it exists
    if command_message:
        full_response = f"{command_message}\n\n"
        message_placeholder.markdown(full_response)
    
    # Process and format the AI response
    formatted_response = process_response(response.text)
    
    # Split into chunks for streaming effect
    chunks = []
    for line in formatted_response.split('\n'):
        chunks.extend(line.split(' '))
        chunks.append('\n')
    
    # Stream the response chunks with typing effect
    for chunk in chunks:
        if chunk != '\n':
            full_response += chunk + ' '
        else:
            full_response += chunk
        time.sleep(0.02)
        message_placeholder.markdown(full_response + "▌", unsafe_allow_html=True)
    
    # Display final response without cursor
    message_placeholder.markdown(full_response, unsafe_allow_html=True)
    return full_response
    
def show_file_preview(uploaded_file):
    mime_type = detect_file_type(uploaded_file)
    
    if mime_type.startswith('image/'):
        st.sidebar.image(uploaded_file, use_container_width=True)
    elif mime_type.startswith('video/'):
        st.sidebar.video(uploaded_file)
    elif mime_type.startswith('audio/'):
        st.sidebar.audio(uploaded_file)
    else:
        st.sidebar.info(f"Uploaded: {uploaded_file.name} (Type: {mime_type})")

def prepare_chat_input(prompt, files):
    input_parts = []
    
    for file in files:
        mime_type = detect_file_type(file)
        content = None
        
        try:
            if mime_type.startswith('application/pdf'):
                content = extract_pdf_text(file)
            elif mime_type in ['application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
                content = extract_docx_text(file)
            elif mime_type.startswith('image/'):
                content = extract_image_text(file)
            elif mime_type in ['text/csv', 'application/json', 'application/xml', 'text/plain']:
                content = process_structured_data(file, mime_type)
            
            if content:
                input_parts.append({
                    'type': mime_type,
                    'content': content,
                    'name': file.name
                })
        except Exception as e:
            st.error(f"Error processing {file.name}: {str(e)}")
            continue
    
    input_parts.append(prompt)
    return input_parts

def main():
    initialize_session_state()

    st.title("📙 ESL at Home - AI Chatbot")
    #st.divider()
    
    # Display messages in the main chat area (outside the sidebar)
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"], unsafe_allow_html=True)

    # Chat input handling
    prompt = st.chat_input("What information can I provide?")

    if prompt:
        final_prompt = prompt
        command_suffix = ""
        command_message = ""
        
        if hasattr(st.session_state, 'current_command') and st.session_state.current_command:
            command = st.session_state.current_command
            
            # Check if it's a built-in command or custom command
            if command in PREBUILT_COMMANDS:
                command_prompt = PREBUILT_COMMANDS[command]["prompt"]
                command_suffix = f" **[{command}]**"
                command_message = PREBUILT_COMMANDS[command].get("message_text", "")
            elif command in st.session_state.custom_commands:
                command_prompt = st.session_state.custom_commands[command]["prompt"]
                command_suffix = f" **[{command}]**"
                command_message = st.session_state.custom_commands[command].get("message_text", "")
            
            final_prompt = f"{command_prompt}\n{prompt}"
            st.session_state.current_command = None

        input_parts = []
        
        if st.session_state.uploaded_files:
            for file in st.session_state.uploaded_files:
                input_parts.append({
                    'mime_type': detect_file_type(file),
                    'data': file.getvalue()
                })
        
        if st.session_state.camera_image:
            input_parts.append({
                'mime_type': 'image/jpeg',
                'data': st.session_state.camera_image.getvalue()
            })

        input_parts.append(final_prompt)

        st.chat_message("user").markdown(prompt + command_suffix)
        st.session_state.messages.append({"role": "user", "content": prompt + command_suffix})
        
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            
            try:
                response = st.session_state.chat_session.send_message(input_parts)
                full_response = handle_chat_response(response, message_placeholder)
                
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": full_response
                })
                
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
                if "rate_limit" in str(e).lower():
                    st.warning("The API rate limit has been reached. Please wait a moment before trying again.")
                else:
                    st.warning("Please try again in a moment.")

        if st.session_state.camera_image and not st.session_state.camera_enabled:
            st.session_state.camera_image = None

if __name__ == "__main__":
    main()
