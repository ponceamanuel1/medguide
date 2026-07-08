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
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from supabase import create_client, Client

# Configuration
# Configuration
UPLOAD_FOLDER = tempfile.gettempdir()
MAX_CONTENT_LENGTH = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

app = Flask(__name__)
app.secret_key = os.urandom(24)

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
        text = message.content[0].text
        # Strip markdown formatting
        import re
        text = re.sub(r'#{1,6}\s*', '', text)
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        text = re.sub(r'_{1,2}(.*?)_{1,2}', r'\1', text)
        text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'^[-•]\s', '', text, flags=re.MULTILINE)
        # Remove emojis
        emoji_pattern = re.compile("["
            u"\U0001F600-\U0001F64F"
            u"\U0001F300-\U0001F5FF"
            u"\U0001F680-\U0001F9FF"
            u"\U00002702-\U000027B0"
            "]+", flags=re.UNICODE)
        text = emoji_pattern.sub('', text)
        return text.strip()
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

CRITICAL FORMATTING RULES - STRICTLY FOLLOW THESE OR THE RESPONSE WILL BE REJECTED:
- NEVER use # or ## or ### for headers
- NEVER use ** or * or _ for bold or italic
- NEVER use --- for dividers
- NEVER use > for blockquotes
- NEVER use emojis of any kind
- NEVER start bullet points with - or *
- Write ONLY plain text paragraphs separated by blank lines

RESPONSE STRUCTURE - use these exact plain text labels:
Write "Context:" then your explanation paragraph.
Write "Check-In:" then 1-2 caring questions as plain sentences.
Write "Questions for Your Doctor:" then number them 1. 2. 3. as plain text.
Write "Important:" for any warnings as a plain paragraph.

RULES:
- You do NOT diagnose or prescribe - only educate
- ONLY use information from peer-reviewed sources: PubMed, NIH, CDC, FDA, Mayo Clinic
- Never invent statistics or studies
- Always include exactly 3 numbered doctor questions
- Be warm, supportive, and conversational
- If someone mentions crisis or self-harm, provide crisis resources immediately

End with: "Always consult your healthcare provider for personalized advice."

TONE: Warm, supportive, conversational - like a knowledgeable friend who cares."""

    lang_map = {
        'es': '\n\nRespond entirely in Spanish. Use these Spanish section labels exactly: "Contexto:" instead of "Context:", "Consulta:" instead of "Check-In:", "Preguntas para tu Médico:" instead of "Questions for Your Doctor:", "Importante:" instead of "Important:", and "Siempre consulta a tu proveedor de salud para consejos personalizados." instead of "Always consult your healthcare provider for personalized advice."',
        'zh': '\n\nRespond entirely in Simplified Chinese. Use these Chinese section labels: "背景：" instead of "Context:", "问询：" instead of "Check-In:", "向您的医生提问：" instead of "Questions for Your Doctor:", "重要：" instead of "Important:", "请始终咨询您的医疗保健提供者以获取个性化建议。" instead of the final disclaimer.',
        'fr': '\n\nRespond entirely in French. Use these French section labels: "Contexte :" instead of "Context:", "Vérification :" instead of "Check-In:", "Questions pour votre Médecin :" instead of "Questions for Your Doctor:", "Important :" instead of "Important:", "Consultez toujours un professionnel de santé pour des conseils personnalisés." instead of the final disclaimer.',
        'de': '\n\nRespond entirely in German. Use these German section labels: "Kontext:" instead of "Context:", "Nachfrage:" instead of "Check-In:", "Fragen für Ihren Arzt:" instead of "Questions for Your Doctor:", "Wichtig:" instead of "Important:", "Konsultieren Sie immer einen Arzt für persönliche Beratung." instead of the final disclaimer.',
        'pt': '\n\nRespond entirely in Portuguese. Use these Portuguese section labels: "Contexto:" instead of "Context:", "Verificação:" instead of "Check-In:", "Perguntas para o seu Médico:" instead of "Questions for Your Doctor:", "Importante:" instead of "Important:", "Consulte sempre um profissional de saúde para aconselhamento personalizado." instead of the final disclaimer.',
        'ja': '\n\nRespond entirely in Japanese. Use these Japanese section labels: "背景：" instead of "Context:", "確認：" instead of "Check-In:", "医師への質問：" instead of "Questions for Your Doctor:", "重要：" instead of "Important:", "個別のアドバイスについては、必ず医療専門家に相談してください。" instead of the final disclaimer.',
        'ko': '\n\nRespond entirely in Korean. Use these Korean section labels: "배경：" instead of "Context:", "확인：" instead of "Check-In:", "의사에게 물어볼 질문：" instead of "Questions for Your Doctor:", "중요：" instead of "Important:", "개인화된 조언을 위해 항상 의료 전문가와 상담하세요." instead of the final disclaimer.',
        'ar': '\n\nRespond entirely in Arabic. Use these Arabic section labels: "السياق:" instead of "Context:", "تحقق:" instead of "Check-In:", "أسئلة لطبيبك:" instead of "Questions for Your Doctor:", "مهم:" instead of "Important:", "استشر دائماً مقدم الرعاية الصحية للحصول على نصيحة شخصية." instead of the final disclaimer.',
        'hi': '\n\nRespond entirely in Hindi. Use these Hindi section labels: "संदर्भ:" instead of "Context:", "जाँच:" instead of "Check-In:", "अपने डॉक्टर के लिए प्रश्न:" instead of "Questions for Your Doctor:", "महत्वपूर्ण:" instead of "Important:", "व्यक्तिगत सलाह के लिए हमेशा स्वास्थ्य सेवा प्रदाता से परामर्श करें।" instead of the final disclaimer.',
    }
    return base + lang_map.get(language, '')

@app.route("/")
def login():
    return render_template("login.html")

@app.route("/app")
def index():
    return render_template("index.html",
        session_user_id=session.get('user_id', ''),
        session_email=session.get('email', '')
    )

@app.route('/auth/signup', methods=['POST'])
def auth_signup():
    try:
        data = request.json or {}
        email = data.get('email', '').strip()
        password = data.get('password', '')

        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password are required'}), 400

        result = supabase.auth.sign_up({
            'email': email,
            'password': password
        })

        if result.user:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Sign up failed. Please try again.'})

    except Exception as e:
        error_msg = str(e)
        print(f"Signup error: {error_msg}")
        if 'already registered' in error_msg.lower() or 'already been registered' in error_msg.lower():
            return jsonify({'success': False, 'error': 'An account with this email already exists. Please sign in instead.'})
        return jsonify({'success': False, 'error': 'Sign up failed. Please try again.'}), 500


@app.route('/auth/signin', methods=['POST'])
def auth_signin():
    try:
        data = request.json or {}
        email = data.get('email', '').strip()
        password = data.get('password', '')

        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password are required'}), 400

        result = supabase.auth.sign_in_with_password({
            'email': email,
            'password': password
        })

        if result.user:
            session['user_id'] = result.user.id
            session['email'] = result.user.email
            return jsonify({
                'success': True,
                'user_id': result.user.id,
                'email': result.user.email
            })
        else:
            return jsonify({'success': False, 'error': 'Invalid email or password.'})

    except Exception as e:
        error_msg = str(e)
        print(f"Signin error: {error_msg}")
        if 'invalid' in error_msg.lower() or 'credentials' in error_msg.lower():
            return jsonify({'success': False, 'error': 'Invalid email or password.'})
        if 'email not confirmed' in error_msg.lower():
            return jsonify({'success': False, 'error': 'Please verify your email first. Check your inbox for a verification link.'})
        return jsonify({'success': False, 'error': 'Sign in failed. Please try again.'}), 500

@app.route('/save-profile', methods=['POST'])
def save_profile():
    try:
        data = request.json or {}
        user_id = data.get("user_id")

        profile_data = {
            "age_range": data.get("age", ""),
            "gender": data.get("gender", ""),
            "ethnicity": data.get("ethnicity", ""),
            "diet": data.get("diet", ""),
            "allergies": data.get("allergies", ""),
            "alcohol": data.get("alcohol", ""),
            "smoking": data.get("smoking", ""),
            "mobility": data.get("mobility", ""),
            "goals": data.get("goals", ""),
            "insurance": data.get("insurance", ""),
            "conditions": data.get("conditions", []),
            "priorities": data.get("priorities", []),
            "language": data.get("language", "en"),
            "user_id": user_id,
        }

        # If user is logged in, check if profile already exists and update it
        if user_id:
            existing = supabase.table("profiles")\
                .select("id")\
                .eq("user_id", user_id)\
                .limit(1)\
                .execute()

            if existing.data:
                # Update existing profile
                profile_id = existing.data[0]["id"]
                supabase.table("profiles")\
                    .update(profile_data)\
                    .eq("id", profile_id)\
                    .execute()
                return jsonify({"success": True, "profile_id": profile_id})

        # No existing profile - insert new one
        result = supabase.table("profiles").insert(profile_data).execute()
        profile_id = result.data[0]["id"] if result.data else None
        return jsonify({"success": True, "profile_id": profile_id})

    except Exception as e:
        print(f"Save profile error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    
@app.route('/get-profile', methods=['GET'])
def get_profile():
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'No user_id provided'}), 400

        result = supabase.table("profiles")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()

        if result.data:
            return jsonify({'success': True, 'profile': result.data[0]})
        else:
            return jsonify({'success': False, 'profile': None})

    except Exception as e:
        print(f"Get profile error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/get-chat-history', methods=['GET'])
def get_chat_history():
    try:
        profile_id = request.args.get('profile_id')
        if not profile_id:
            return jsonify({'success': False, 'messages': []})

        result = supabase.table("chat_messages")\
            .select("*")\
            .eq("profile_id", profile_id)\
            .order("created_at", desc=False)\
            .limit(20)\
            .execute()

        return jsonify({'success': True, 'messages': result.data or []})

    except Exception as e:
        print(f"Get chat history error: {e}")
        return jsonify({'success': False, 'messages': []}), 500
    
@app.route('/generate-report', methods=['POST'])
def generate_report():
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from flask import send_file
        import io
        from datetime import datetime

        data = request.json or {}
        messages = data.get('messages', [])
        profile = data.get('profile', {})
        wellbeing = data.get('wellbeing', {})
        language = data.get('language', 'en')
        print(f"Generating report in language: {language}")

        # Language labels
        pdf_labels = {
            'en': {'summary': 'Patient Health Summary', 'profile': 'Patient Profile', 'feeling': 'How the Patient is Feeling', 'physical': 'Physical Comfort', 'emotional': 'Emotional State', 'notes': 'Patient Notes', 'conversation': 'Conversation Summary', 'asked': 'Patient asked:', 'explained': 'MedGuide explained:', 'footer': 'Generated by MedGuide', 'disclaimer': 'This document is for educational purposes only. Always consult a qualified healthcare professional.', 'warning': 'This summary is for educational purposes only and does not constitute medical advice. Please share with your healthcare provider.'},
            'es': {'summary': 'Resumen de Salud del Paciente', 'profile': 'Perfil del Paciente', 'feeling': 'Cómo se Siente el Paciente', 'physical': 'Comodidad Física', 'emotional': 'Estado Emocional', 'notes': 'Notas del Paciente', 'conversation': 'Resumen de la Conversación', 'asked': 'El paciente preguntó:', 'explained': 'MedGuide explicó:', 'footer': 'Generado por MedGuide', 'disclaimer': 'Este documento es solo para fines educativos. Siempre consulte a un profesional de salud calificado.', 'warning': 'Este resumen es solo para fines educativos y no constituye consejo médico.'},
            'zh': {'summary': '患者健康摘要', 'profile': '患者档案', 'feeling': '患者的感受', 'physical': '身体舒适度', 'emotional': '情绪状态', 'notes': '患者备注', 'conversation': '对话摘要', 'asked': '患者问道：', 'explained': 'MedGuide解释：', 'footer': '由MedGuide生成', 'disclaimer': '本文件仅供教育目的。请咨询合格的医疗专业人员。', 'warning': '本摘要仅供教育目的，不构成医疗建议。'},
            'fr': {'summary': 'Résumé de Santé du Patient', 'profile': 'Profil du Patient', 'feeling': 'Comment le Patient se Sent', 'physical': 'Confort Physique', 'emotional': 'État Émotionnel', 'notes': 'Notes du Patient', 'conversation': 'Résumé de la Conversation', 'asked': 'Le patient a demandé :', 'explained': 'MedGuide a expliqué :', 'footer': 'Généré par MedGuide', 'disclaimer': 'Ce document est à des fins éducatives uniquement. Consultez toujours un professionnel de santé qualifié.', 'warning': 'Ce résumé est à des fins éducatives uniquement et ne constitue pas un avis médical.'},
            'de': {'summary': 'Gesundheitszusammenfassung des Patienten', 'profile': 'Patientenprofil', 'feeling': 'Wie sich der Patient fühlt', 'physical': 'Körperliches Wohlbefinden', 'emotional': 'Emotionaler Zustand', 'notes': 'Patientennotizen', 'conversation': 'Gesprächszusammenfassung', 'asked': 'Der Patient fragte:', 'explained': 'MedGuide erklärte:', 'footer': 'Erstellt von MedGuide', 'disclaimer': 'Dieses Dokument dient nur zu Bildungszwecken. Konsultieren Sie immer einen qualifizierten Arzt.', 'warning': 'Diese Zusammenfassung dient nur zu Bildungszwecken und stellt keine medizinische Beratung dar.'},
            'pt': {'summary': 'Resumo de Saúde do Paciente', 'profile': 'Perfil do Paciente', 'feeling': 'Como o Paciente está se Sentindo', 'physical': 'Conforto Físico', 'emotional': 'Estado Emocional', 'notes': 'Notas do Paciente', 'conversation': 'Resumo da Conversa', 'asked': 'O paciente perguntou:', 'explained': 'MedGuide explicou:', 'footer': 'Gerado por MedGuide', 'disclaimer': 'Este documento é apenas para fins educacionais. Sempre consulte um profissional de saúde qualificado.', 'warning': 'Este resumo é apenas para fins educacionais e não constitui conselho médico.'},
            'ja': {'summary': '患者の健康サマリー', 'profile': '患者プロフィール', 'feeling': '患者の状態', 'physical': '身体的な快適さ', 'emotional': '精神的な状態', 'notes': '患者メモ', 'conversation': '会話の要約', 'asked': '患者の質問：', 'explained': 'MedGuideの説明：', 'footer': 'MedGuideによって生成', 'disclaimer': 'この文書は教育目的のみです。常に資格のある医療専門家に相談してください。', 'warning': 'このサマリーは教育目的のみであり、医療アドバイスを構成するものではありません。'},
            'ko': {'summary': '환자 건강 요약', 'profile': '환자 프로필', 'feeling': '환자의 상태', 'physical': '신체적 편안함', 'emotional': '감정 상태', 'notes': '환자 메모', 'conversation': '대화 요약', 'asked': '환자가 물었습니다:', 'explained': 'MedGuide가 설명했습니다:', 'footer': 'MedGuide에서 생성', 'disclaimer': '이 문서는 교육 목적으로만 사용됩니다. 항상 자격을 갖춘 의료 전문가와 상담하세요.', 'warning': '이 요약은 교육 목적으로만 사용되며 의료 조언을 구성하지 않습니다.'},
            'ar': {'summary': 'ملخص صحة المريض', 'profile': 'ملف المريض', 'feeling': 'كيف يشعر المريض', 'physical': 'الراحة الجسدية', 'emotional': 'الحالة العاطفية', 'notes': 'ملاحظات المريض', 'conversation': 'ملخص المحادثة', 'asked': 'سأل المريض:', 'explained': 'شرح MedGuide:', 'footer': 'تم إنشاؤه بواسطة MedGuide', 'disclaimer': 'هذه الوثيقة لأغراض تعليمية فقط. استشر دائماً متخصصاً في الرعاية الصحية.', 'warning': 'هذا الملخص لأغراض تعليمية فقط ولا يشكل نصيحة طبية.'},
            'hi': {'summary': 'रोगी स्वास्थ्य सारांश', 'profile': 'रोगी प्रोफ़ाइल', 'feeling': 'रोगी कैसा महसूस कर रहा है', 'physical': 'शारीरिक आराम', 'emotional': 'भावनात्मक स्थिति', 'notes': 'रोगी नोट्स', 'conversation': 'बातचीत सारांश', 'asked': 'रोगी ने पूछा:', 'explained': 'MedGuide ने समझाया:', 'footer': 'MedGuide द्वारा उत्पन्न', 'disclaimer': 'यह दस्तावेज़ केवल शैक्षिक उद्देश्यों के लिए है। हमेशा एक योग्य स्वास्थ्य पेशेवर से परामर्श करें।', 'warning': 'यह सारांश केवल शैक्षिक उद्देश्यों के लिए है और चिकित्सा सलाह नहीं है।'},
        }
        lbl = pdf_labels.get(language, pdf_labels['en'])
        print(f"Profile gender value: '{profile.get('gender')}'")
        print(f"Profile diet value: '{profile.get('diet')}'")
        print(f"Profile smoking value: '{profile.get('smoking')}'")

        # Build PDF in memory
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )

        styles = getSampleStyleSheet()
        story = []

        # Custom styles
        title_style = ParagraphStyle('Title',
            parent=styles['Heading1'],
            fontSize=22,
            textColor=colors.HexColor('#1e3a8a'),
            spaceAfter=4,
            alignment=TA_CENTER
        )
        subtitle_style = ParagraphStyle('Subtitle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#6b7280'),
            spaceAfter=2,
            alignment=TA_CENTER
        )
        section_style = ParagraphStyle('Section',
            parent=styles['Heading2'],
            fontSize=13,
            textColor=colors.HexColor('#1e3a8a'),
            spaceBefore=16,
            spaceAfter=6
        )
        body_style = ParagraphStyle('Body',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#374151'),
            spaceAfter=4,
            leading=16
        )
        label_style = ParagraphStyle('Label',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#6b7280'),
            spaceAfter=2
        )
        disclaimer_style = ParagraphStyle('Disclaimer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#9ca3af'),
            alignment=TA_CENTER,
            spaceAfter=4
        )

        # Header
        story.append(Paragraph('MedGuide', title_style))
        story.append(Paragraph(lbl['summary'], subtitle_style))
        story.append(Paragraph(datetime.now().strftime('%B %d, %Y at %I:%M %p'), subtitle_style))
        story.append(Spacer(1, 12))
        story.append(HRFlowable(width='100%', thickness=2, color=colors.HexColor('#1e3a8a')))
        story.append(Spacer(1, 12))

        # Disclaimer
        story.append(Paragraph(lbl['warning'], disclaimer_style))
        story.append(Spacer(1, 8))

        # Patient Profile
        if profile:
            story.append(Paragraph(lbl['profile'], section_style))
            story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#e5e7eb')))
            story.append(Spacer(1, 6))
        
            #Translate profile values
            value_map = {
                'es': {
                    'male': 'Masculino', 'female': 'Femenino', 'other': 'Otro',
                    'regular': 'Regular', 'vegetarian': 'Vegetariano', 'vegan': 'Vegano',
                    'halal': 'Halal', 'kosher': 'Kosher', 'glutenfree': 'Sin gluten',
                    'none': 'Ninguno', 'occasional': 'Ocasional', 'moderate': 'Moderado', 'daily': 'Diario',
                    'never': 'Nunca fumé', 'former': 'Ex fumador', 'current': 'Fumador actual',
                    'full': 'Totalmente móvil', 'limited': 'Algunas limitaciones', 'assistive': 'Usa dispositivos',
                },
                'zh': {
                    'male': '男', 'female': '女', 'other': '其他',
                    'regular': '普通', 'vegetarian': '素食', 'vegan': '纯素食',
                    'halal': '清真', 'kosher': '犹太洁食', 'glutenfree': '无麸质',
                    'none': '无', 'occasional': '偶尔', 'moderate': '适度', 'daily': '每天',
                    'never': '从不吸烟', 'former': '曾经吸烟', 'current': '目前吸烟',
                    'full': '完全行动自如', 'limited': '有些限制', 'assistive': '使用辅助设备',
                },
                'fr': {
                    'male': 'Masculin', 'female': 'Féminin', 'other': 'Autre',
                    'regular': 'Normal', 'vegetarian': 'Végétarien', 'vegan': 'Végétalien',
                    'halal': 'Halal', 'kosher': 'Casher', 'glutenfree': 'Sans gluten',
                    'none': 'Aucun', 'occasional': 'Occasionnel', 'moderate': 'Modéré', 'daily': 'Quotidien',
                    'never': 'Jamais fumé', 'former': 'Ancien fumeur', 'current': 'Fumeur actuel',
                    'full': 'Pleinement mobile', 'limited': 'Quelques limitations', 'assistive': 'Utilise des aides',
                },
                'de': {
                    'male': 'Männlich', 'female': 'Weiblich', 'other': 'Andere',
                    'regular': 'Normal', 'vegetarian': 'Vegetarisch', 'vegan': 'Vegan',
                    'halal': 'Halal', 'kosher': 'Koscher', 'glutenfree': 'Glutenfrei',
                    'none': 'Keiner', 'occasional': 'Gelegentlich', 'moderate': 'Mäßig', 'daily': 'Täglich',
                    'never': 'Nie geraucht', 'former': 'Ehemaliger Raucher', 'current': 'Aktueller Raucher',
                    'full': 'Voll mobil', 'limited': 'Einige Einschränkungen', 'assistive': 'Nutzt Hilfsmittel',
                },
                'pt': {
                    'male': 'Masculino', 'female': 'Feminino', 'other': 'Outro',
                    'regular': 'Regular', 'vegetarian': 'Vegetariano', 'vegan': 'Vegano',
                    'halal': 'Halal', 'kosher': 'Kosher', 'glutenfree': 'Sem glúten',
                    'none': 'Nenhum', 'occasional': 'Ocasional', 'moderate': 'Moderado', 'daily': 'Diário',
                    'never': 'Nunca fumou', 'former': 'Ex-fumante', 'current': 'Fumante atual',
                    'full': 'Totalmente móvel', 'limited': 'Algumas limitações', 'assistive': 'Usa dispositivos',
                },
                'ja': {
                    'male': '男性', 'female': '女性', 'other': 'その他',
                    'regular': '通常', 'vegetarian': 'ベジタリアン', 'vegan': 'ビーガン',
                    'halal': 'ハラール', 'kosher': 'コーシャ', 'glutenfree': 'グルテンフリー',
                    'none': 'なし', 'occasional': 'たまに', 'moderate': '適度', 'daily': '毎日',
                    'never': '吸ったことがない', 'former': '以前は吸っていた', 'current': '現在吸っている',
                    'full': '完全に動ける', 'limited': '一部制限あり', 'assistive': '補助器具を使用',
                },
                'ko': {
                    'male': '남성', 'female': '여성', 'other': '기타',
                    'regular': '일반', 'vegetarian': '채식주의자', 'vegan': '비건',
                    'halal': '할랄', 'kosher': '코셔', 'glutenfree': '글루텐 프리',
                    'none': '없음', 'occasional': '가끔', 'moderate': '적당히', 'daily': '매일',
                    'never': '피운 적 없음', 'former': '전 흡연자', 'current': '현재 흡연자',
                    'full': '완전 이동 가능', 'limited': '일부 제한', 'assistive': '보조 기구 사용',
                },
                'ar': {
                    'male': 'ذكر', 'female': 'أنثى', 'other': 'آخر',
                    'regular': 'عادي', 'vegetarian': 'نباتي', 'vegan': 'نباتي صرف',
                    'halal': 'حلال', 'kosher': 'كوشر', 'glutenfree': 'خالٍ من الغلوتين',
                    'none': 'لا شيء', 'occasional': 'أحياناً', 'moderate': 'معتدل', 'daily': 'يومياً',
                    'never': 'لم أدخن أبداً', 'former': 'مدخن سابق', 'current': 'مدخن حالي',
                    'full': 'متحرك بالكامل', 'limited': 'بعض القيود', 'assistive': 'أستخدم أدوات مساعدة',
                },
                'hi': {
                    'male': 'पुरुष', 'female': 'महिला', 'other': 'अन्य',
                    'regular': 'सामान्य', 'vegetarian': 'शाकाहारी', 'vegan': 'शुद्ध शाकाहारी',
                    'halal': 'हलाल', 'kosher': 'कोशर', 'glutenfree': 'ग्लूटेन-मुक्त',
                    'none': 'कोई नहीं', 'occasional': 'कभी-कभी', 'moderate': 'मध्यम', 'daily': 'रोज़ाना',
                    'never': 'कभी नहीं पिया', 'former': 'पूर्व धूम्रपानी', 'current': 'वर्तमान धूम्रपानी',
                    'full': 'पूर्ण गतिशील', 'limited': 'कुछ सीमाएं', 'assistive': 'सहायक उपकरण का उपयोग',
                },
            }

            def translate_value(value, lang):
                if not value:
                    return ''
                vm = value_map.get(lang, {})
                result = vm.get(value.lower(), value.capitalize())
                print(f"translate_value: '{value}' -> '{result}' (lang={lang})")
                return vm.get(value.lower(), value.capitalize())

            profile_data = []
            if profile.get('age'): profile_data.append(['Age Range', profile['age']])
            if profile.get('gender'): profile_data.append(['Biological Sex', profile['gender'].capitalize()])
            if profile.get('diet'): profile_data.append(['Diet', profile['diet'].capitalize()])
            if profile.get('allergies'): profile_data.append(['Food Allergies', profile['allergies']])
            if profile.get('smoking'): profile_data.append(['Smoking Status', profile['smoking'].capitalize()])
            if profile.get('alcohol'): profile_data.append(['Alcohol Use', profile['alcohol'].capitalize()])
            if profile.get('insurance'): profile_data.append(['Insurance', profile['insurance'].capitalize()])
            if profile.get('conditions') and len(profile['conditions']) > 0:
                profile_data.append(['Health Conditions', ', '.join(profile['conditions'])])
            if profile.get('mobility'): profile_data.append(['Mobility', profile['mobility'].capitalize()])

            if profile_data:
                t = Table(profile_data, colWidths=[2*inch, 4.5*inch])
                t.setStyle(TableStyle([
                    ('FONTSIZE', (0,0), (-1,-1), 9),
                    ('TEXTCOLOR', (0,0), (0,-1), colors.HexColor('#6b7280')),
                    ('TEXTCOLOR', (1,0), (1,-1), colors.HexColor('#374151')),
                    ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
                    ('ROWBACKGROUNDS', (0,0), (-1,-1), [colors.HexColor('#f8fafc'), colors.white]),
                    ('PADDING', (0,0), (-1,-1), 6),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e5e7eb')),
                ]))
                story.append(t)

        # Wellbeing Section
        story.append(Paragraph(lbl['feeling'], section_style))
        story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#e5e7eb')))
        story.append(Spacer(1, 6))

        physical = wellbeing.get('physical')
        emotional = wellbeing.get('emotional')
        notes = wellbeing.get('notes', '')

        def score_label(score, type):
            if score is None:
                return 'Not provided'
            if type == 'physical':
                labels = {1: 'Severe discomfort', 2: 'Significant discomfort', 3: 'Moderate discomfort', 4: 'Some discomfort', 5: 'Moderate', 6: 'Mostly comfortable', 7: 'Good', 8: 'Very good', 9: 'Excellent', 10: 'Feeling fine'}
            else:
                labels = {1: 'Very anxious/scared', 2: 'Very anxious', 3: 'Anxious', 4: 'Somewhat anxious', 5: 'Neutral', 6: 'Mostly calm', 7: 'Calm', 8: 'Good', 9: 'Very confident', 10: 'Calm and confident'}
            return f'{score}/10 — {labels.get(score, "")}'

        wellbeing_data = [
            [lbl['physical'], score_label(physical, 'physical')],
            [lbl['emotional'], score_label(emotional, 'emotional')],
        ]
        if notes:
            wellbeing_data.append([lbl['notes'], notes])

        wt = Table(wellbeing_data, colWidths=[2*inch, 4.5*inch])
        wt.setStyle(TableStyle([
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('TEXTCOLOR', (0,0), (0,-1), colors.HexColor('#6b7280')),
            ('TEXTCOLOR', (1,0), (1,-1), colors.HexColor('#374151')),
            ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
            ('ROWBACKGROUNDS', (0,0), (-1,-1), [colors.HexColor('#fefce8'), colors.white]),
            ('PADDING', (0,0), (-1,-1), 6),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e5e7eb')),
        ]))
        story.append(wt)

        # Conversation Summary
        story.append(Paragraph(lbl['conversation'], section_style))
        story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#e5e7eb')))
        story.append(Spacer(1, 6))

        for msg in messages:
            role = msg.get('role', '')
            content = msg.get('content', '').strip()
            if not content:
                continue
            if role == 'user':
                story.append(Paragraph('<b>' + lbl['asked'] + '</b>', label_style))
                story.append(Paragraph(content, body_style))
            else:
                story.append(Paragraph('<b>' + lbl['explained'] + '</b>', label_style))
                content = content.replace('**', '')
                story.append(Paragraph(content[:800] + ('...' if len(content) > 800 else ''), body_style))
            story.append(Spacer(1, 4))

        # Footer
        story.append(Spacer(1, 16))
        story.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#e5e7eb')))
        story.append(Spacer(1, 8))
        story.append(Paragraph(lbl['footer'] + ' — medguide-production-434d.up.railway.app', disclaimer_style))
        story.append(Paragraph(lbl['disclaimer'], disclaimer_style))

        doc.build(story)
        buffer.seek(0)

        return send_file(
            buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name='MedGuide_Report.pdf'
        )

    except Exception as e:
        print(f"Report generation error: {e}")
        return jsonify({'error': str(e)}), 500

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
        
        force = request.form.get('force', 'false') == 'true'

        # First, detect if document is medical
        if force:
            category = "MEDICAL"
        else:
            detection_prompt = f"""Look at this document and classify it into one of three categories:
1. MEDICAL - clearly a medical document (lab results, prescriptions, doctor notes, discharge summaries, imaging reports, medical bills, insurance EOBs with medical codes, pharmacy receipts)
2. AMBIGUOUS - could have medical relevance (general insurance documents, wellness documents, anything with some health terms)
3. NOT_MEDICAL - clearly not medical (school assignments, report cards, essays, business documents, legal contracts, receipts for non-medical items)

Respond with ONLY a JSON object like this:
{{"category": "MEDICAL", "reason": "brief reason"}}

Document text:
{text[:2000]}"""

        detection_response = ollama_chat(get_system_prompt(language), detection_prompt)
        
        category = "MEDICAL"
        try:
            match = re.search(r'\{[\s\S]*\}', detection_response)
            if match:
                detection = json.loads(match.group())
                category = detection.get('category', 'MEDICAL').upper()
        except:
            category = "MEDICAL"

        # Handle based on category
        if category == "NOT_MEDICAL":
            return jsonify({
                'success': True,
                'analysis': {
                    'document_type': 'Non-Medical Document',
                    'key_findings': [],
                    'general_meaning': 'I am unable to analyze this document as it does not appear to be a medical document. MedGuide is designed to help you understand medical records, lab results, prescriptions, and other health-related documents. Please upload a medical document and I will be happy to help explain it in plain language.',
                    'questions_for_doctor': [],
                    'not_medical': True
                }
            })
        
        if category == "AMBIGUOUS":
            return jsonify({
                'success': True,
                'analysis': {
                    'document_type': 'Unclear Document Type',
                    'key_findings': [],
                    'general_meaning': 'This does not appear to be a typical medical document. Are you sure this is medical related? If you would like me to move forward, I can analyze it and translate any medical terms I find into plain language and give you the best explanation I can.',
                    'questions_for_doctor': [],
                    'ambiguous': True
                }
            })

        # Clearly medical - analyze normally
        prompt = f"""Analyze this medical document and respond in plain text (no markdown, no hashtags, no bullet points with dashes).

Structure your response as JSON:
{{"document_type":"type of medical document","key_findings":["finding 1","finding 2"],"general_meaning":"plain language explanation of what this document means","questions_for_doctor":["question 1","question 2","question 3"]}}

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
    port = int(os.environ.get("PORT", 5050))
    app.run(debug=False, host="0.0.0.0", port=port)