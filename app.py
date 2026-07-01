"""
MedGuide - Health Understanding Assistant
Complete Flask backend with chat, hospital search, and document analysis
"""

import requests
import re
import os
import tempfile
import json
import anthropic
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from supabase import create_client, Client

# Configuration
# Configuration
UPLOAD_FOLDER = tempfile.gettempdir()
MAX_CONTENT_LENGTH = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

app = Flask(__name__)

load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("Missing Supabase information in .env")

supabase: Client = create_client(
    supabase_url,
    supabase_key
)

app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def ollama_chat(system_prompt, user_prompt):
    try:
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        return message.content[0].text
    except Exception as e:
        print(f"Anthropic error: {e}")
        return None

# Crisis keywords in all 10 languages
CRISIS_KEYWORDS = [
    # English
    "kill myself", "end my life", "suicide", "suicidal", "want to die",
    "better off dead", "no reason to live", "can't go on", "end it all",
    "hurt myself", "self-harm", "don't want to live", "take my life",
    "no point in living", "wish i was dead", "rather be dead", "wanting to die",
    "thoughts of suicide", "kill me", "end it", "not worth living",
    # Spanish
    "matarme", "suicidarme", "quiero morir", "no quiero vivir", "acabar con todo",
    "sin razón para vivir", "hacerme daño", "autolesión", "mejor muerto",
    "no vale la pena vivir", "quitarme la vida", "pensamientos suicidas",
    # Chinese
    "自杀", "想死", "不想活", "结束生命", "活不下去", "自我伤害",
    "没有活下去的理由", "想要死", "轻生", "寻死",
    # French
    "me suicider", "me tuer", "envie de mourir", "en finir", "plus envie de vivre",
    "mettre fin à mes jours", "automutilation", "pensées suicidaires",
    # German
    "umbringen", "selbstmord", "nicht mehr leben", "sterben wollen", "suizid",
    "lebensmüde", "selbstverletzung", "das leben beenden",
    # Portuguese
    "me matar", "suicídio", "quero morrer", "acabar com tudo", "não quero viver",
    "sem razão para viver", "autolesão", "tirar minha vida",
    # Japanese
    "自殺", "死にたい", "生きたくない", "死のう", "命を絶つ", "自傷",
    "生きる意味がない", "死んでしまいたい",
    # Korean
    "자살", "죽고 싶", "살고 싶지 않", "삶을 끝내고", "자해",
    "사는 게 의미없", "죽어버리고 싶",
    # Arabic
    "انتحار", "أريد الموت", "قتل نفسي", "إنهاء حياتي", "لا أريد العيش",
    "إيذاء النفس", "أفكار انتحارية",
    # Hindi
    "आत्महत्या", "मरना चाहता", "जीना नहीं चाहता", "खुद को मारना",
    "जीने का कोई कारण नहीं", "आत्म-हानि"
]

MEDICAL_EMERGENCY_KEYWORDS = [
    "chest pain", "chest pains", "heart attack", "having a heart attack",
    "can't breathe", "cannot breathe", "trouble breathing", "stopped breathing",
    "not breathing", "stroke", "having a stroke", "face drooping", "arm weakness",
    "severe bleeding", "bleeding out", "won't stop bleeding",
    "unconscious", "passed out", "unresponsive",
    "overdose", "took too many pills", "swallowed too much",
    "allergic reaction", "throat closing", "anaphylaxis",
    "seizure", "having a seizure",
]

CRISIS_RESPONSES = {
    'en': """I hear you, and I'm really glad you reached out. What you're feeling matters, and you don't have to face this alone.

I want you to know that these feelings, as overwhelming as they are right now, can get better with the right support. You deserve care and compassion.

**Please reach out for support right now:**

• **988 Suicide & Crisis Lifeline**: Call or text **988** (available 24/7, free, confidential, multilingual support available)
• **Crisis Text Line**: Text **HOME** to **741741**
• **Emergency**: Call **911** or go to your nearest emergency room

These are people who understand what you're going through and genuinely want to help. You don't have to have it all figured out - just reaching out is a brave first step.

You matter. Your life has value. And there are people ready to support you through this.""",

    'es': """Te escucho, y me alegra mucho que hayas decidido hablar. Lo que sientes es importante, y no tienes que enfrentar esto solo/a.

Quiero que sepas que estos sentimientos, aunque ahora parezcan abrumadores, pueden mejorar con el apoyo adecuado. Mereces cuidado y compasión.

**Por favor, busca apoyo ahora mismo:**

• **Línea 988**: Llama o envía mensaje de texto al **988** (disponible 24/7, gratis, confidencial, apoyo en español disponible)
• **Crisis Text Line**: Envía **HOME** al **741741**
• **Emergencias**: Llama al **911** o ve a la sala de emergencias más cercana

Hay personas que entienden lo que estás pasando y genuinamente quieren ayudar. No necesitas tener todo resuelto - simplemente pedir ayuda es un primer paso valiente.

Tú importas. Tu vida tiene valor. Y hay personas listas para apoyarte.""",

    'zh': """我听到你了，我真的很高兴你愿意说出来。你的感受很重要，你不必独自面对这一切。

我想让你知道，这些感受虽然现在看起来难以承受，但在正确的支持下是可以好转的。你值得被关心和爱护。

**请现在就寻求帮助：**

• **988自杀与危机生命线**：拨打或发短信至 **988**（全天候服务，免费，保密，有多语言支持）
• **危机短信热线**：发送 **HOME** 到 **741741**
• **紧急情况**：拨打 **911** 或前往最近的急诊室

这些人理解你正在经历的一切，真心想要帮助你。你不需要把一切都想清楚——寻求帮助本身就是勇敢的第一步。

你很重要。你的生命有价值。有人准备好支持你度过这段时期。""",

    'fr': """Je t'entends, et je suis vraiment content(e) que tu aies décidé de parler. Ce que tu ressens est important, et tu n'as pas à affronter cela seul(e).

Je veux que tu saches que ces sentiments, aussi accablants qu'ils puissent paraître maintenant, peuvent s'améliorer avec le bon soutien. Tu mérites attention et compassion.

**S'il te plaît, cherche du soutien maintenant :**

• **Ligne 988**: Appelle ou envoie un SMS au **988** (disponible 24h/24, gratuit, confidentiel, support multilingue disponible)
• **Crisis Text Line**: Envoie **HOME** au **741741**
• **Urgences**: Appelle le **911** ou va aux urgences les plus proches

Ce sont des personnes qui comprennent ce que tu traverses et qui veulent sincèrement t'aider. Tu n'as pas besoin d'avoir toutes les réponses - simplement demander de l'aide est un premier pas courageux.

Tu comptes. Ta vie a de la valeur. Et il y a des personnes prêtes à te soutenir.""",

    'de': """Ich höre dich, und ich bin wirklich froh, dass du dich gemeldet hast. Was du fühlst, ist wichtig, und du musst das nicht alleine durchstehen.

Ich möchte, dass du weißt, dass diese Gefühle, so überwältigend sie jetzt auch sein mögen, mit der richtigen Unterstützung besser werden können. Du verdienst Fürsorge und Mitgefühl.

**Bitte suche jetzt Unterstützung:**

• **988 Krisenhotline**: Anrufen oder SMS an **988** (24/7 verfügbar, kostenlos, vertraulich, mehrsprachige Unterstützung)
• **Crisis Text Line**: Sende **HOME** an **741741**
• **Notfall**: Rufe **911** an oder gehe zur nächsten Notaufnahme

Das sind Menschen, die verstehen, was du durchmachst, und die dir wirklich helfen wollen. Du musst nicht alles geklärt haben - einfach um Hilfe zu bitten ist ein mutiger erster Schritt.

Du bist wichtig. Dein Leben hat Wert. Und es gibt Menschen, die bereit sind, dich zu unterstützen.""",

    'pt': """Eu ouço você, e fico muito feliz que você decidiu falar. O que você está sentindo é importante, e você não precisa enfrentar isso sozinho/a.

Quero que você saiba que esses sentimentos, por mais avassaladores que pareçam agora, podem melhorar com o apoio certo. Você merece cuidado e compaixão.

**Por favor, busque apoio agora:**

• **Linha 988**: Ligue ou envie mensagem para **988** (disponível 24/7, gratuito, confidencial, suporte multilíngue disponível)
• **Crisis Text Line**: Envie **HOME** para **741741**
• **Emergência**: Ligue **911** ou vá ao pronto-socorro mais próximo

São pessoas que entendem o que você está passando e genuinamente querem ajudar. Você não precisa ter tudo resolvido - simplesmente pedir ajuda é um primeiro passo corajoso.

Você importa. Sua vida tem valor. E há pessoas prontas para apoiá-lo/a.""",

    'ja': """あなたの声を聞いています。話してくれて本当にうれしいです。あなたの気持ちは大切です。一人で抱え込む必要はありません。

今は圧倒されているかもしれませんが、適切なサポートがあれば、これらの気持ちは良くなることができます。あなたはケアと思いやりを受ける価値があります。

**今すぐサポートを求めてください：**

• **988自殺・危機ライフライン**：**988** に電話またはテキスト（24時間対応、無料、秘密厳守、多言語サポートあり）
• **Crisis Text Line**：**741741** に **HOME** とテキスト
• **緊急時**：**911** に電話するか、最寄りの救急病院へ

これらは、あなたが経験していることを理解し、心から助けたいと思っている人たちです。すべてを解決する必要はありません - 助けを求めること自体が勇敢な第一歩です。

あなたは大切な存在です。あなたの命には価値があります。そして、あなたをサポートする準備ができている人がいます。""",

    'ko': """당신의 이야기를 듣고 있어요. 이야기해 주셔서 정말 기뻐요. 당신이 느끼는 감정은 중요합니다. 혼자서 이겨내지 않아도 됩니다.

지금은 압도당하는 것처럼 느껴질 수 있지만, 올바른 지원을 받으면 이러한 감정들은 나아질 수 있습니다. 당신은 보살핌과 연민을 받을 자격이 있습니다.

**지금 바로 도움을 요청해 주세요:**

• **988 자살 및 위기 상담 전화**: **988**로 전화 또는 문자 (24시간 운영, 무료, 비밀 보장, 다국어 지원 가능)
• **Crisis Text Line**: **741741**로 **HOME** 문자
• **응급상황**: **911**에 전화하거나 가까운 응급실로 가세요

이들은 당신이 겪고 있는 것을 이해하고 진심으로 도와주고 싶어하는 사람들입니다. 모든 것을 해결할 필요는 없어요 - 도움을 요청하는 것 자체가 용감한 첫걸음입니다.

당신은 소중합니다. 당신의 삶에는 가치가 있습니다. 그리고 당신을 지원할 준비가 된 사람들이 있습니다.""",

    'ar': """أنا أسمعك، وأنا سعيد حقاً أنك قررت التحدث. ما تشعر به مهم، ولا يجب أن تواجه هذا بمفردك.

أريدك أن تعرف أن هذه المشاعر، مهما بدت ساحقة الآن، يمكن أن تتحسن مع الدعم المناسب. أنت تستحق الرعاية والتعاطف.

**من فضلك اطلب الدعم الآن:**

• **خط 988 للانتحار والأزمات**: اتصل أو أرسل رسالة نصية إلى **988** (متاح على مدار الساعة، مجاني، سري، دعم متعدد اللغات متاح)
• **Crisis Text Line**: أرسل **HOME** إلى **741741**
• **الطوارئ**: اتصل بـ **911** أو اذهب لأقرب غرفة طوارئ

هؤلاء أشخاص يفهمون ما تمر به ويريدون مساعدتك بصدق. لا تحتاج إلى حل كل شيء - مجرد طلب المساعدة هو خطوة أولى شجاعة.

أنت مهم. حياتك لها قيمة. وهناك أشخاص مستعدون لدعمك.""",

    'hi': """मैं आपकी बात सुन रहा/रही हूं, और मुझे खुशी है कि आपने बात करने का फैसला किया। आप जो महसूस कर रहे हैं वह महत्वपूर्ण है, और आपको इसका अकेले सामना नहीं करना है।

मैं चाहता/चाहती हूं कि आप जानें कि ये भावनाएं, भले ही अभी बहुत भारी लग रही हों, सही सहायता से बेहतर हो सकती हैं। आप देखभाल और करुणा के योग्य हैं।

**कृपया अभी सहायता लें:**

• **988 आत्महत्या और संकट हेल्पलाइन**: **988** पर कॉल या टेक्स्ट करें (24/7 उपलब्ध, मुफ्त, गोपनीय, बहुभाषी सहायता उपलब्ध)
• **Crisis Text Line**: **741741** पर **HOME** टेक्स्ट करें
• **आपातकाल**: **911** पर कॉल करें या निकटतम आपातकालीन कक्ष में जाएं

ये ऐसे लोग हैं जो समझते हैं कि आप किस दौर से गुजर रहे हैं और सच में आपकी मदद करना चाहते हैं। आपको सब कुछ सुलझाने की जरूरत नहीं है - बस मदद मांगना एक साहसी पहला कदम है।

आप महत्वपूर्ण हैं। आपके जीवन का मूल्य है। और ऐसे लोग हैं जो आपका साथ देने के लिए तैयार हैं।"""
}
MEDICAL_EMERGENCY_RESPONSES = {
    'en': """🚨 **This sounds like a medical emergency. Call 911 immediately.**

Do not wait — call **911** right now or have someone nearby call for you.

**While waiting for help:**
- Stay as calm as possible
- Don't eat or drink anything
- Unlock your door if you can so paramedics can get in
- Stay on the phone with the 911 operator — they will guide you

**If someone is unconscious and not breathing:** start CPR if you know how. The 911 operator can walk you through it.

MedGuide is an educational tool and cannot provide emergency medical care. **Call 911 now.**""",

    'es': """🚨 **Esto suena como una emergencia médica. Llama al 911 inmediatamente.**

No esperes — llama al **911** ahora mismo o pide a alguien cercano que llame.

**Mientras esperas ayuda:**
- Mantén la calma
- No comas ni bebas nada
- Desbloquea tu puerta si puedes para que los paramédicos puedan entrar
- Permanece en el teléfono con el operador del 911

**Llama al 911 ahora.**""",

    'zh': """🚨 **这听起来像是医疗紧急情况。请立即拨打911。**

不要等待——现在就拨打**911**，或让附近的人帮您拨打。

**等待救援时：**
- 尽量保持冷静
- 不要吃喝任何东西
- 如果可以，解锁门让急救人员进入
- 保持与911接线员通话

**请立即拨打911。**""",

    'fr': """🚨 **Cela ressemble à une urgence médicale. Appelez le 911 immédiatement.**

N'attendez pas — appelez le **911** maintenant ou demandez à quelqu'un nearby d'appeler.

**En attendant les secours:**
- Restez aussi calme que possible
- Ne mangez ni ne buvez rien
- Déverrouillez votre porte si vous pouvez
- Restez en ligne avec l'opérateur du 911

**Appelez le 911 maintenant.**""",

    'de': """🚨 **Das klingt nach einem medizinischen Notfall. Rufen Sie sofort 911 an.**

Warten Sie nicht — rufen Sie jetzt **911** an oder bitten Sie jemanden in der Nähe.

**Während Sie auf Hilfe warten:**
- Bleiben Sie so ruhig wie möglich
- Essen oder trinken Sie nichts
- Entsperren Sie Ihre Tür wenn möglich
- Bleiben Sie in der Leitung mit dem 911-Operator

**Rufen Sie jetzt 911 an.**""",

    'pt': """🚨 **Isso parece uma emergência médica. Ligue para o 911 imediatamente.**

Não espere — ligue para o **911** agora ou peça a alguém próximo que ligue.

**Enquanto aguarda ajuda:**
- Fique o mais calmo possível
- Não coma nem beba nada
- Desbloqueie sua porta se puder
- Fique na linha com o operador do 911

**Ligue para o 911 agora.**""",

    'ja': """🚨 **これは医療緊急事態のようです。今すぐ911に電話してください。**

待たないでください — 今すぐ**911**に電話するか、近くにいる人に電話してもらってください。

**助けを待つ間：**
- できるだけ落ち着いてください
- 何も食べたり飲んだりしないでください
- できればドアのロックを解除してください
- 911のオペレーターと電話を続けてください

**今すぐ911に電話してください。**""",

    'ko': """🚨 **의료 응급 상황인 것 같습니다. 즉시 911에 전화하세요.**

기다리지 마세요 — 지금 바로 **911**에 전화하거나 근처 사람에게 전화를 부탁하세요.

**도움을 기다리는 동안:**
- 최대한 침착하게 있으세요
- 아무것도 먹거나 마시지 마세요
- 가능하면 문을 잠금 해제하세요
- 911 교환원과 통화를 유지하세요

**지금 바로 911에 전화하세요.**""",

    'ar': """🚨 **يبدو هذا حالة طوارئ طبية. اتصل بـ 911 فوراً.**

لا تنتظر — اتصل بـ **911** الآن أو اطلب من شخص قريب الاتصال.

**أثناء انتظار المساعدة:**
- ابق هادئاً قدر الإمكان
- لا تأكل أو تشرب أي شيء
- افتح باب منزلك إذا استطعت
- ابق على الهاتف مع مشغل 911

**اتصل بـ 911 الآن.**""",

    'hi': """🚨 **यह एक चिकित्सा आपातकाल लगता है। तुरंत 911 पर कॉल करें।**

प्रतीक्षा न करें — अभी **911** पर कॉल करें या पास के किसी व्यक्ति से कॉल करवाएं।

**मदद का इंतजार करते समय:**
- जितना हो सके शांत रहें
- कुछ भी न खाएं या पिएं
- अगर हो सके तो दरवाजा खोल दें
- 911 ऑपरेटर से फोन पर जुड़े रहें

**अभी 911 पर कॉल करें।**"""
}

def check_crisis(text, language='en'):
    text_lower = text.lower()
    
    # Check medical emergencies first
    for keyword in MEDICAL_EMERGENCY_KEYWORDS:
        if keyword in text_lower:
            return True, MEDICAL_EMERGENCY_RESPONSES.get(language, MEDICAL_EMERGENCY_RESPONSES['en'])
    
    # Then check mental health crisis keywords
    for keyword in CRISIS_KEYWORDS:
        if keyword in text_lower:
            return True, CRISIS_RESPONSES.get(language, CRISIS_RESPONSES['en'])
    
    return False, None

def get_system_prompt(language='en'):
    base = """You are MedGuide, a warm, caring health education assistant.

CRITICAL RULES:
- You do NOT diagnose or prescribe - only educate
- ONLY use information from peer-reviewed sources: PubMed, NIH, CDC, FDA, Mayo Clinic, Cleveland Clinic, WHO, Cochrane Library
- If you're unsure or information isn't well-established, say so clearly
- Never invent statistics or studies

RESPONSE FORMAT (follow this structure):

1. **CONTEXT** (1-2 paragraphs): Briefly explain what's happening in simple terms. Help them understand the basics of their situation, medication, or condition. Be warm and reassuring.

2. **CHECK-IN**: Ask 1-2 caring questions about what concerns them most. Examples:
   - "What aspect of this worries you the most?"
   - "Are you experiencing any specific symptoms that concern you?"
   - "Is there something particular about this that's been on your mind?"

3. **QUESTIONS FOR YOUR DOCTOR** (always include exactly 3):
   - Question 1: About their specific situation
   - Question 2: About treatment options or management
   - Question 3: About lifestyle, prevention, or next steps

End with: "Always consult your healthcare provider for personalized advice."

TONE: Warm, supportive, conversational - like a knowledgeable friend who cares."""

    lang_map = {
        'es': '\n\nRespond entirely in Spanish.',
        'zh': '\n\nRespond entirely in Simplified Chinese.',
        'fr': '\n\nRespond entirely in French.',
        'de': '\n\nRespond entirely in German.',
        'pt': '\n\nRespond entirely in Portuguese.',
        'ja': '\n\nRespond entirely in Japanese.',
        'ko': '\n\nRespond entirely in Korean.',
        'ar': '\n\nRespond entirely in Arabic.',
        'hi': '\n\nRespond entirely in Hindi.',
    }
    return base + lang_map.get(language, '')

@app.route("/")
def index():
    return render_template("index.html")

@app.route('/save-profile', methods=['POST'])
def save_profile():
    """Saves a completed onboarding profile to Supabase and returns its ID."""
    try:
        data = request.json or {}

        result = supabase.table("profiles").insert({
            "age_range": data.get("age", ""),
            "gender": data.get("gender", ""),
            "ethnicity": data.get("ethnicity", ""),
            "diet": data.get("diet", ""),
            "allergies": data.get("allergies", ""),
            "alcohol": data.get("alcohol", ""),
            "smoking": data.get("smoking", ""),
            "mobility": data.get("mobility", ""),
            "goals": data.get("goals", ""),
            "conditions": data.get("conditions", []),
            "priorities": data.get("priorities", []),
            "language": data.get("language", "en"),
        }).execute()

        profile_id = result.data[0]["id"] if result.data else None
        return jsonify({"success": True, "profile_id": profile_id})

    except Exception as e:
        print(f"Save profile error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/save-message', methods=['POST'])
def save_message():
    """Logs a single chat message (user or assistant) to Supabase."""
    try:
        data = request.json or {}

        supabase.table("chat_messages").insert({
            "profile_id": data.get("profile_id"),
            "role": data.get("role"),
            "content": data.get("content", ""),
            "is_crisis": data.get("is_crisis", False),
            "language": data.get("language", "en"),
        }).execute()

        return jsonify({"success": True})

    except Exception as e:
        print(f"Save message error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    
@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        message = data.get('message', '').strip()
        context = data.get('context', {})
        language = context.get('language', 'en')
        
        if not message:
            return jsonify({'error': 'Please enter a message'}), 400
        
        is_crisis, crisis_response = check_crisis(message, language)
        if is_crisis:
            profile_id = context.get('profile_id')
            if profile_id:
                try:
                    supabase.table("chat_messages").insert([
                        {
                            "profile_id": profile_id,
                            "role": "user",
                            "content": message,
                            "is_crisis": True,
                            "language": language,
                        },
                        {
                            "profile_id": profile_id,
                            "role": "assistant",
                            "content": crisis_response,
                            "is_crisis": True,
                            "language": language,
                        },
                    ]).execute()
                except Exception as log_err:
                    print(f"Crisis logging error (non-fatal): {log_err}")
            return jsonify({'response': crisis_response, 'is_crisis': True})
        
        # Build context from form fields
        parts = []
        if context.get('medications'): parts.append(f"Current Medications: {context['medications']}")
        if context.get('supplements'): parts.append(f"Supplements: {context['supplements']}")
        if context.get('conditions'): parts.append(f"Health Conditions: {context['conditions']}")
        if context.get('symptoms'): parts.append(f"Current Symptoms: {context['symptoms']}")
        if context.get('ageRange'): parts.append(f"Age Range: {context['ageRange']}")
        
        # Add profile data if available
        profile = context.get('profile')
        if profile:
            if profile.get('gender'): parts.append(f"Biological Sex: {profile['gender']}")
            if profile.get('ethnicity') and profile['ethnicity'] != '': parts.append(f"Ethnic Background: {profile['ethnicity']}")
            if profile.get('diet'): parts.append(f"Diet: {profile['diet']}")
            if profile.get('allergies'): parts.append(f"Food Allergies: {profile['allergies']}")
            if profile.get('alcohol'): parts.append(f"Alcohol Use: {profile['alcohol']}")
            if profile.get('smoking'): parts.append(f"Smoking Status: {profile['smoking']}")
            if profile.get('mobility'): parts.append(f"Mobility Level: {profile['mobility']}")
            if profile.get('surgeries'): parts.append(f"Past Surgeries: {profile['surgeries']}")
            if profile.get('conditions') and len(profile['conditions']) > 0:
                parts.append(f"Health Conditions from Profile: {', '.join(profile['conditions'])}")
            if profile.get('priorities') and len(profile['priorities']) > 0:
                parts.append(f"Health Priorities: {', '.join(profile['priorities'])}")
            if profile.get('goals'): parts.append(f"Health Goals: {profile['goals']}")
        
        context_str = "\n".join(parts) if parts else "No additional context."
        user_prompt = f"Patient Context:\n{context_str}\n\nQuestion: {message}\n\nProvide a helpful, educational response. Consider the patient's background, lifestyle, and priorities when relevant."
        
        response = ollama_chat(get_system_prompt(language), user_prompt)
        if response:
            profile_id = context.get('profile_id')
            if profile_id:
                try:
                    supabase.table("chat_messages").insert([
                        {
                            "profile_id": profile_id,
                            "role": "user",
                            "content": message,
                            "is_crisis": False,
                            "language": language,
                        },
                        {
                            "profile_id": profile_id,
                            "role": "assistant",
                            "content": response,
                            "is_crisis": False,
                            "language": language,
                        },
                    ]).execute()
                except Exception as log_err:
                    print(f"Chat logging error (non-fatal): {log_err}")
            return jsonify({'response': response})
        return jsonify({'error': 'Unable to get response'}), 500
            
    except Exception as e:
        print(f"Chat error: {e}")
        return jsonify({'error': 'Error processing request'}), 500

@app.route('/geocode', methods=['GET'])
def geocode():
    location = request.args.get('location', '').strip()
    if not location:
        return jsonify({'error': 'Please provide a location'}), 400
    
    try:
        # If it looks like a US ZIP code, add "USA" for better results
        search_query = location
        if location.isdigit() and len(location) == 5:
            search_query = f"{location}, USA"
        
        r = requests.get("https://nominatim.openstreetmap.org/search",
                        params={'q': search_query, 'format': 'json', 'limit': 1, 'addressdetails': 1},
                        headers={'User-Agent': 'MedGuide/1.0'}, timeout=10)
        data = r.json()
        
        if data:
            return jsonify({
                'lat': float(data[0]['lat']),
                'lon': float(data[0]['lon']),
                'name': data[0].get('display_name', location)
            })
        return jsonify({'error': 'Location not found. Try adding city or state.'}), 404
    except Exception as e:
        print(f"Geocode error: {e}")
        return jsonify({'error': 'Error finding location'}), 500

@app.route('/hospitals', methods=['GET'])
def hospitals():
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        radius = int(request.args.get('radius', 16093))
    except Exception as e:
        print(f"Invalid coordinates: {e}")
        return jsonify({'error': 'Invalid coordinates'}), 400
    
    try:
        query = f"""[out:json][timeout:25];
(node["amenity"="hospital"](around:{radius},{lat},{lon});
way["amenity"="hospital"](around:{radius},{lat},{lon});
node["healthcare"="hospital"](around:{radius},{lat},{lon}););
out center body;"""
        
        print(f"Searching hospitals near {lat}, {lon} with radius {radius}m")
        r = requests.post("https://overpass-api.de/api/interpreter",
                         data={'data': query}, timeout=30,
                         headers={'User-Agent': 'MedGuide/1.0'})
        r.raise_for_status()
        data = r.json()
        print(f"Found {len(data.get('elements', []))} elements")
        
        from math import radians, sin, cos, sqrt, atan2
        hospitals = []
        seen = set()
        
        for el in data.get('elements', []):
            tags = el.get('tags', {})
            name = tags.get('name', 'Medical Facility')
            if name in seen: continue
            seen.add(name)
            
            if el['type'] == 'node':
                h_lat, h_lon = el['lat'], el['lon']
            else:
                center = el.get('center', {})
                h_lat, h_lon = center.get('lat'), center.get('lon')
            
            if not h_lat or not h_lon: continue
            
            R = 3959
            lat1, lon1, lat2, lon2 = map(radians, [lat, lon, h_lat, h_lon])
            dlat, dlon = lat2 - lat1, lon2 - lon1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            distance = R * 2 * atan2(sqrt(a), sqrt(1-a))
            
            hospitals.append({
                'name': name, 'lat': h_lat, 'lon': h_lon,
                'distance': round(distance, 1),
                'address': tags.get('addr:street', ''),
                'city': tags.get('addr:city', ''),
                'phone': tags.get('phone', ''),
                'emergency': tags.get('emergency') == 'yes' or 'emergency' in name.lower()
            })
        
        hospitals.sort(key=lambda x: x['distance'])
        print(f"Returning {len(hospitals[:15])} hospitals")
        return jsonify({'hospitals': hospitals[:15]})
    except requests.exceptions.Timeout:
        print("Overpass API timeout")
        return jsonify({'error': 'Search timed out. Please try again.'}), 504
    except requests.exceptions.RequestException as e:
        print(f"Network error: {e}")
        return jsonify({'error': 'Network error. Please check your connection.'}), 503
    except Exception as e:
        print(f"Hospital error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Error searching hospitals. Please try again.'}), 500

@app.route('/analyze-document', methods=['POST'])
def analyze_document():
    temp_path = None
    try:
        if 'document' not in request.files:
            return jsonify({'error': 'No document uploaded'}), 400
        
        file = request.files['document']
        language = request.form.get('language', 'en')
        
        if not file.filename or not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type'}), 400
        
        filename = secure_filename(file.filename)
        temp_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(temp_path)
        
        text = ""
        if filename.lower().endswith('.pdf'):
            try:
                import fitz
                doc = fitz.open(temp_path)
                for page in doc: text += page.get_text()
                doc.close()
            except:
                pass
        else:
            try:
                import pytesseract
                from PIL import Image
                text = pytesseract.image_to_string(Image.open(temp_path))
            except:
                pass
        
        if len(text.strip()) < 10:
            return jsonify({'error': 'Could not extract text'}), 400
        
        prompt = f"""Analyze this medical document. Respond in JSON format:
{{"document_type":"type","key_findings":["finding1"],"general_meaning":"explanation","questions_for_doctor":["question1"]}}

Document: {text[:3000]}"""
        
        response = ollama_chat(get_system_prompt(language), prompt)
        
        if response:
            try:
                match = re.search(r'\{[\s\S]*\}', response)
                analysis = json.loads(match.group()) if match else {
                    "document_type": "Medical Document",
                    "key_findings": ["Document analyzed"],
                    "general_meaning": response[:500],
                    "questions_for_doctor": ["Review with your doctor"]
                }
            except:
                analysis = {
                    "document_type": "Medical Document",
                    "key_findings": ["Document analyzed"],
                    "general_meaning": response[:500],
                    "questions_for_doctor": ["Review with your doctor"]
                }
            return jsonify({'success': True, 'analysis': analysis})
        
        return jsonify({'error': 'Analysis failed'}), 500
    except Exception as e:
        print(f"Document error: {e}")
        return jsonify({'error': 'Error analyzing document'}), 500
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

if __name__ == "__main__":
    print("=" * 50)
    print("MedGuide Server Starting")
    print("Ensure Ollama is running: ollama run llama3.1")
    print("=" * 50)
    app.run(debug=True, host="127.0.0.1", port=5050)