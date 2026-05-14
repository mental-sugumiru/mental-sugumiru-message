# 医師マッピング（resourceId → tagId）
DOCTOR_MAP = {
    "cmocd9sle1jbr132u7lrcljco": {"name": "三宅先生", "tag_id": "cmov5u7d51ml12g2t1zwqpdhx"},
    "cmocdc3bl1jc6132um4ekjsvy": {"name": "京先生",   "tag_id": "cmov5udip1ml32g2tdme2rvdt"},
    "cmnr5cr372maa2c2t6jn9qx9l": {"name": "釜先生",   "tag_id": "cmov5urwy1ml52g2txzgs2lii"},
    "cmocdb7z31jbw132unidyuerl": {"name": "清水先生", "tag_id": "cmov5v19q1ml92g2tkkicqme0"},
    "cmocdbrrw1jc4132ulqjud185": {"name": "宮路先生", "tag_id": "cmov5v8ca1mlb2g2tazpir2sq"},
}

# 「時間帯で予約」フォームIDのみ対象（個別フォームは既存ステップ配信が拾うので除外）
TARGET_FORM_IDS = {
    "cmnsbhdas10ov2c2v2iexo8fv",  # 初診_時間帯で予約
    "cmnr65bi42mfm2c2tm67wnovi",  # 再診_時間帯で予約
}

BOT_ID = "cmnr5c12j2m9x2c2thjihlv5a"
ORGANIZATION_ID = "cmnr5c0xl2m9u2c2toh4rvbn7"
CLINIC_ID = "cmnr5c12o2m9z2c2tvvrh31l7"

MEDIBOT_BASE = "https://medibot.cloud"