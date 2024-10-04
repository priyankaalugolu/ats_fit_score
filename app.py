import streamlit as st
import pdfplumber
from docx import Document
import re
import requests
import pandas as pd
import boto3

st.write("# **Applicant Tracking System (ATS)📑**")

# Initialize session state to store slider values
if 'weights' not in st.session_state:
    st.session_state.weights = {
        'skills_matching': 40,
        'experience': 30,
        'education': 20,
        'keyword_usage': 10,
        'certifications': 0,
        'achievements': 0,
        'job_stability': 0,
        'cultural_fit': 0
    }

# Function to normalize the weights to sum up to 100%
def normalize_weights():
    total_weight = sum(st.session_state.weights.values())
    if total_weight != 0:
        for key in st.session_state.weights:
            st.session_state.weights[key] = (st.session_state.weights[key] / total_weight) * 100

# Sliders for each evaluation criterion
st.write("### Adjust Scoring Percentages (Total should be 100%)")
st.session_state.weights['skills_matching'] = st.slider("Skills Matching (%)", 0, 100, st.session_state.weights['skills_matching'], 1)
st.session_state.weights['experience'] = st.slider("Relevant Experience (%)", 0, 100, st.session_state.weights['experience'], 1)
st.session_state.weights['education'] = st.slider("Education and Certifications (%)", 0, 100, st.session_state.weights['education'], 1)
st.session_state.weights['keyword_usage'] = st.slider("Keyword Usage (%)", 0, 100, st.session_state.weights['keyword_usage'], 1)
st.session_state.weights['certifications'] = st.slider("Certifications (%)", 0, 100, st.session_state.weights['certifications'], 1)
st.session_state.weights['achievements'] = st.slider("Achievements (%)", 0, 100, st.session_state.weights['achievements'], 1)
st.session_state.weights['job_stability'] = st.slider("Job Stability (%)", 0, 100, st.session_state.weights['job_stability'], 1)
st.session_state.weights['cultural_fit'] = st.slider("Cultural Fit (%)", 0, 100, st.session_state.weights['cultural_fit'], 1)

# Display the sum of weights
total_weight = sum(st.session_state.weights.values())
st.write(f"Total Weight: {total_weight:.2f}%")

# Check if the total weight is 100%
if total_weight != 100:
    st.warning("The total weight must be 100% before uploading files.")

# Initialize boto3 client for S3
s3_client = boto3.client(
    's3',
    aws_access_key_id=st.secrets["aws"]["aws_access_key_id"],
    aws_secret_access_key=st.secrets["aws"]["aws_secret_access_key"],
    region_name=st.secrets["aws"]["aws_region"]
)

def extract_text_from_pdf(pdf_file):
    text = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text += page.extract_text()
    return text

def extract_text_from_docx(word_file):
    doc = Document(word_file)
    text = ""
    for para in doc.paragraphs:
        text += para.text
    return text

def preprocess_text(text):
    text = re.sub(r'\n+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    processed_text = text.strip()
    return processed_text

def call_chatgpt_api(prompt, api_key):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": prompt}]
    }
    response = requests.post("https://api.openai.com/v1/chat/completions", json=data, headers=headers)
    response_json = response.json()
    return response_json

def extract_ats_score(response_content):
    score_match = re.search(r'ATS\s*Score.*?(\d{1,3})\s*(out\s*of\s*100)?', response_content, re.IGNORECASE)
    if score_match:
        return int(score_match.group(1))
    return None

def upload_to_s3(file, bucket_name, file_name):
    s3_client.upload_fileobj(file, bucket_name, file_name)

def main():
    # File uploaders
    uploaded_resumes = st.file_uploader("Upload CV/Resume(s)", ['pdf', 'docx', 'txt'], accept_multiple_files=True)
    uploaded_job_description = st.file_uploader("Upload Job Description", ['pdf', 'docx', 'txt'])

    if uploaded_resumes and uploaded_job_description:
        if total_weight != 100:
            st.error("The total weight of all categories must be 100% before processing. Please adjust the sliders.")
            return

        # Normalize weights before processing
        normalize_weights()

        if uploaded_job_description.type == 'application/pdf':
            job_description = extract_text_from_pdf(uploaded_job_description)
        elif uploaded_job_description.type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            job_description = extract_text_from_docx(uploaded_job_description)
        
        job_description = preprocess_text(job_description)

        api_key = st.secrets["general"]["OPENAI_API_KEY"]

        filtered_resumes = []
        unfiltered_resumes = []

        for uploaded_resume in uploaded_resumes:
            resume_text = None
            if uploaded_resume.type == 'application/pdf':
                resume_text = extract_text_from_pdf(uploaded_resume)
            elif uploaded_resume.type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                resume_text = extract_text_from_docx(uploaded_resume)

            resume_text = preprocess_text(resume_text)

            prompt = f"""
                Please evaluate this resume and job description for ATS compatibility.

                The following criteria should be considered when evaluating:
                1. **Skills Matching** ({st.session_state.weights['skills_matching']}% of total score): Match the listed skills in the resume against the job description. Focus on both technical and soft skills.
                2. **Relevant Experience** ({st.session_state.weights['experience']}% of total score): Evaluate the relevance of the candidate's work experience to the job description.
                3. **Education and Certifications** ({st.session_state.weights['education']}% of total score): Check the alignment of the candidate's education and certifications with the job requirements.
                4. **Keyword Usage** ({st.session_state.weights['keyword_usage']}% of total score): Look for key terms mentioned in the job description and ensure they are present in the resume.
                5. **Certifications** ({st.session_state.weights['certifications']}% of total score): Evaluate the candidate's certifications in relation to the job requirements.
                6. **Achievements** ({st.session_state.weights['achievements']}% of total score): Highlight any quantified achievements in the resume that match the job description.
                7. **Job Stability** ({st.session_state.weights['job_stability']}% of total score): Assess job stability, such as gaps in employment or frequent job switches.
                8. **Cultural Fit** ({st.session_state.weights['cultural_fit']}% of total score): Check how well the candidate's background aligns with the company's culture and values.
                
                Resume: {resume_text}
                Job Description: {job_description}

                Provide the following:
                - A detailed ATS Score out of 100 based on the rubric above. Consistency across evaluations is crucial.
                - Validate the contact information (Email, Phone, LinkedIn).
                - Provide a summary of experience and education alignment.
                - List the skills found in the resume and how they match the job description.
                - Highlight any quantified achievements mentioned in the resume.
                - Assess job stability (e.g., gaps in employment or frequent job switches).
                - Explain how well the resume aligns with the job description.
                Ensure the evaluation process is consistent and does not vary between different attempts. Focus on accuracy and providing a fair assessment based on the criteria outlined above.
                """

            response = call_chatgpt_api(prompt, api_key)
            ats_results = response['choices'][0]['message']['content']
            ats_score = extract_ats_score(ats_results)

            if ats_score is not None:
                combined_score = ats_score  # or any logic to calculate combined score

                resume_name = uploaded_resume.name
                if combined_score >= 85:
                    filtered_resumes.append({"Name": resume_name, "ATS Score": combined_score})
                    upload_to_s3(uploaded_resume, "ats-filtered-resumes", resume_name)
                else:
                    unfiltered_resumes.append({"Name": resume_name, "ATS Score": combined_score})
                    upload_to_s3(uploaded_resume, "ats-unfiltered-resumes", resume_name)

        # Display Filtered Resumes
        if filtered_resumes:
            st.write("### Filtered Resumes (ATS Score >= 85%)")
            df_filtered = pd.DataFrame(filtered_resumes)
            st.dataframe(df_filtered)
        else:
            st.write("### Filtered Resumes (ATS Score >= 85%)")
            st.write("0 - No files")

        # Display Unfiltered Resumes
        if unfiltered_resumes:
            st.write("### Unfiltered Resumes (ATS Score < 85%)")
            df_unfiltered = pd.DataFrame(unfiltered_resumes)
            st.dataframe(df_unfiltered)
        else:
            st.write("### Unfiltered Resumes (ATS Score < 85%)")
            st.write("0 - No files")

        # Display upload summary
        st.success(f"{len(filtered_resumes)} files uploaded to Filtered Resumes and {len(unfiltered_resumes)} files uploaded to Unfiltered Resumes!")
        st.balloons()

# Run the main function
main()
