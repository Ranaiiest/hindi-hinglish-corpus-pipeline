import csv, gzip, json, os, random, sys

PAIRS = [
 ("भारत एक विशाल देश है जहाँ अनेक भाषाएँ बोली जाती हैं।", "Bharat ek vishal desh hai jahan anek bhashayein boli jaati hain."),
 ("दिल्ली भारत की राजधानी है और यह यमुना नदी के किनारे बसी है।", "Dilli Bharat ki rajdhani hai aur yeh Yamuna nadi ke kinare basi hai."),
 ("किसान सुबह जल्दी उठकर खेतों में काम करने के लिए निकल जाते हैं।", "Kisan subah jaldi uthkar kheton mein kaam karne ke liye nikal jaate hain."),
 ("विद्यालय में बच्चों को पढ़ाई के साथ खेलकूद की शिक्षा भी दी जाती है।", "Vidyalay mein bachchon ko padhai ke saath khelkood ki shiksha bhi di jaati hai."),
 ("गंगा नदी हिमालय से निकलकर बंगाल की खाड़ी में मिलती है।", "Ganga nadi Himalay se nikalkar Bengal ki khadi mein milti hai."),
 ("आज मौसम बहुत सुहावना है और हल्की बारिश हो रही है।", "Aaj mausam bahut suhavna hai aur halki barish ho rahi hai."),
 ("हमारे देश में त्योहारों का बहुत महत्व है और लोग उन्हें मिलकर मनाते हैं।", "Hamare desh mein tyoharon ka bahut mahatva hai aur log unhe milkar manate hain."),
 ("कंप्यूटर और इंटरनेट ने लोगों के जीवन को बहुत आसान बना दिया है।", "Computer aur internet ne logon ke jeevan ko bahut aasan bana diya hai."),
 ("रेलगाड़ी सुबह छह बजे स्टेशन पर पहुँचेगी इसलिए हमें जल्दी निकलना होगा।", "Railgadi subah chhah baje station par pahunchegi isliye hamein jaldi nikalna hoga."),
 ("मेरे दादाजी हर शाम को बगीचे में टहलने जाते थे।", "Mere dadaji har shaam ko bagiche mein tahalne jaate the."),
 ("सरकार ने ग्रामीण इलाकों में स्वास्थ्य सेवाओं को बेहतर बनाने की घोषणा की है।", "Sarkar ne gramin ilakon mein swasthya sevaon ko behtar banane ki ghoshna ki hai."),
 ("क्रिकेट भारत में सबसे लोकप्रिय खेल माना जाता है।", "Cricket Bharat mein sabse lokpriya khel mana jaata hai."),
 ("पुस्तकालय में बैठकर पढ़ना मुझे बहुत अच्छा लगता है।", "Pustakalay mein baithkar padhna mujhe bahut accha lagta hai."),
 ("ताजमहल आगरा में स्थित है और इसे दुनिया के सात अजूबों में गिना जाता है।", "Tajmahal Agra mein sthit hai aur ise duniya ke saat ajoobon mein gina jaata hai."),
 ("वैज्ञानिकों ने नई खोज के बारे में अपनी रिपोर्ट प्रकाशित की है।", "Vaigyanikon ne nayi khoj ke baare mein apni report prakashit ki hai."),
 ("बाजार में सब्जियों के दाम इस सप्ताह कुछ कम हुए हैं।", "Bazaar mein sabziyon ke daam is saptah kuchh kam hue hain."),
 ("बच्चों के लिए रोज़ सुबह व्यायाम करना और दूध पीना बहुत जरूरी माना जाता है।", "Bachchon ke liye roz subah vyayam karna aur doodh peena bahut zaroori mana jaata hai."),
 ("नदी के किनारे बैठकर शाम का सूरज देखना हर किसी को अच्छा लगता है।", "Nadi ke kinare baithkar shaam ka suraj dekhna har kisi ko accha lagta hai."),
]
HINGLISH = ["Yaar ye movie bahut badhiya thi, tumne dekhi kya? Mujhe toh bahut pasand aayi aur hum phir dekhne jayenge.",
 "Mera phone kharab ho gaya hai aur mujhe naya lena padega, tum kuch suggest kar sakte ho kya?",
 "Bhai tu kab aa raha hai? Ghar pe sab tera wait kar rahe hain aur mummy ne khana bhi bana liya hai.",
 "Kya tum mujhe apna number de sakte ho, main baad mein call karunga aur sab kuch samjha dunga.",
 "Aaj office mein bahut kaam tha isliye main late ghar pahuncha, kal se jaldi aane ki koshish karunga."]
EN = ["The government announced a new policy on Tuesday, and it will be reviewed by the committee before it is approved by the cabinet.",
      "This is a long English paragraph that should be labelled as English because it has the usual function words in it."]
MR = ["माझं नाव राम आहे आणि मी मुंबई मध्ये राहतो. आमच्या शाळेत खूप मुले आहेत आणि ते रोज खेळतात."]
PROVERBS = ["जैसी करनी वैसी भरनी।", "नाच न जाने आँगन टेढ़ा।", "अब पछताए होत क्या जब चिड़िया चुग गई खेत।", "बूँद बूँद से सागर भरता है।"]
POEM = "\n".join(["चलो चलें उस पार", "जहाँ बहती है नदी की धार", "चलो चलें उस पार", "जहाँ मिलता है सबको प्यार", "चलो चलें उस पार", "जहाँ खिलता है हर इक फूल", "चलो चलें उस पार", "जहाँ मिटते हैं सारे शूल"])
TABLE = "वर्ष 2001 2002 2003 2004 2005 2006\nजनसंख्या 102 105 108 112 115 119\nदर 1.2 1.3 1.1 1.4 1.5 1.6"
SPAM = ["वशीकरण विशेषज्ञ बाबा जी काला जादू लव प्रॉब्लम सॉल्यूशन कॉल करें 9876501234 9876501235 9876501236",
        "Best casino betting jackpot click here free download buy now whatsapp me now www.a.com www.b.com www.c.com"]
HTML = "<div class=\"post\"><p>भारत एक देश है</p><span>यह एक परीक्षण है</span><a href=\"x\">link</a></div>"
BOILER = "अधिक पढ़ें\nसर्वाधिकार सुरक्षित\nहमें फॉलो करें\nगोपनीयता नीति\nशेयर करें"

def hi_doc(r, k=None):
    k = k or r.randint(3, 8)
    return " ".join(p[0] for p in r.sample(PAIRS, min(k, len(PAIRS))))

def main(out):
    r = random.Random(7)
    os.makedirs(os.path.join(out, "wiki_like"), exist_ok=True)
    os.makedirs(os.path.join(out, "web_like"), exist_ok=True)
    docs = []
    for i in range(160):
        docs.append({"id": i, "text": hi_doc(r), "lang": "hi"})
    base = docs[3]["text"]
    docs.append({"text": base})
    docs.append({"text": base.replace("।", " । ")})
    docs.append({"text": base.upper() + " कुछ और शब्द यहाँ जोड़े गए हैं"})
    docs += [{"text": p} for p in PROVERBS] + [{"text": POEM}, {"text": TABLE}]
    docs += [{"text": t} for t in SPAM + [HTML, BOILER] + EN + MR]
    docs.append({"text": "फोन 9876543210 ईमेल ravi.k@example.com पैन ABCDE1234F आधार 2345 6789 0123।" + " " + hi_doc(r, 3)})
    docs.append({"text": "नमस्ते दुनिया".encode("utf-8").decode("latin-1") + " " + "यह एक परीक्षण है".encode("utf-8").decode("latin-1")})
    docs.append({"text": "संपर्क ९८७६५४३२१० आधार २३४५ ६७८९ ०१२३।" + " " + hi_doc(r, 3)})
    with open(os.path.join(out, "wiki_like", "part0.jsonl"), "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
        f.write("{this is not json\n"); f.write("\n"); f.write(json.dumps({"nothing": 1}) + "\n")
        f.write(json.dumps({"text": 5}) + "\n")
    with open(os.path.join(out, "wiki_like", "part0.jsonl"), "ab") as f:
        f.write(b"\xff\xfe broken bytes\n")
    hl = [{"text": " ".join(r.sample(HINGLISH, r.randint(2, 4)))} for _ in range(50)]
    hl += [{"text": " ".join(p[1] for p in r.sample(PAIRS, 4))} for _ in range(30)]
    with gzip.open(os.path.join(out, "web_like", "hinglish.jsonl.gz"), "wt", encoding="utf-8") as f:
        for d in hl:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    raw = gzip.compress(("\n".join(json.dumps({"text": hi_doc(r)}, ensure_ascii=False) for _ in range(40))).encode("utf-8"))
    with open(os.path.join(out, "web_like", "truncated.jsonl.gz"), "wb") as f:
        f.write(raw[: int(len(raw) * 0.6)])
    with open(os.path.join(out, "web_like", "news.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["title", "content"])
        for _ in range(60):
            w.writerow(["शीर्षक", hi_doc(r)])
        w.writerow(["only one column"])
    with open(os.path.join(out, "web_like", "lines.txt"), "w", encoding="utf-8") as f:
        for _ in range(20):
            f.write(hi_doc(r, 4) + "\n")
    print("wrote", out)

if __name__ == "__main__":
    main(sys.argv[1])
