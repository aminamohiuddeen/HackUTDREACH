/*
  RESCUE POD — ESP32 firmware (HackUTD)
  Libraries: Adafruit SSD1306, Adafruit GFX, DHT sensor library, Keypad, ArduinoJson
  WIRING (ESP32 DevKit)
    OLED + MPU6050 (I2C) : SDA -> 21, SCL -> 22, VCC -> 3V3, GND -> GND
    PIR (HC-SR501)       : OUT -> 27, VCC -> VIN (5V), GND -> GND
    Sound sensor         : AO  -> 34, VCC -> 3V3
    IR reflective        : DO  -> 35, VCC -> 3V3
    DHT11                : DATA -> 4, VCC -> 3V3
    Buzzer module        : SIG -> 25
    4x4 keypad: rows -> 19,18,5,17  cols -> 16,23,32,33
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>
#include <Keypad.h>

// ================= CONFIG — EDIT THESE =================
const char* WIFI_SSID = "rescuebot";
const char* WIFI_PASS = "lavendar";
// Public URL of the REACH FastAPI backend (uvicorn main:app on port 8000, behind ngrok/cloudflared).
const char* SERVER    = "https://anthology-reheat-mystified.ngrok-free.dev";
const char* UNIT_ID   = "REACH-01";      // sent as robot_id
const char* SECTOR    = "C4";            // grid sector the pod is deployed in
const char* ZONE      = "residential";   // residential | industrial | road | unknown
// =======================================================

#define PIN_PIR     27
#define PIN_SOUND   34
#define PIN_IR      35
#define PIN_DHT     4
#define PIN_BUZZER  25
#define DHTTYPE     DHT11

const int  LOUD_THRESHOLD   = 800;
const unsigned long TELEMETRY_MS = 2000;

Adafruit_SSD1306 display(128, 64, &Wire, -1);

// ---- Raw MPU6050 driver (works with clone / "ITG/MPU" boards) ----
uint8_t mpuAddr = 0;

bool mpuWrite(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(mpuAddr);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

bool mpuInit() {
  uint8_t candidates[2] = {0x68, 0x69};
  for (int i = 0; i < 2; i++) {
    Wire.beginTransmission(candidates[i]);
    if (Wire.endTransmission() == 0) { mpuAddr = candidates[i]; break; }
  }
  if (mpuAddr == 0) return false;
  Wire.beginTransmission(mpuAddr);
  Wire.write(0x75);
  Wire.endTransmission(false);
  Wire.requestFrom(mpuAddr, (uint8_t)1);
  uint8_t who = Wire.available() ? Wire.read() : 0;
  Serial.printf("IMU found at 0x%02X, WHO_AM_I = 0x%02X\n", mpuAddr, who);
  mpuWrite(0x6B, 0x00);   // wake up
  delay(50);
  mpuWrite(0x1B, 0x00);   // gyro  +/-250 deg/s
  mpuWrite(0x1C, 0x10);   // accel +/-8 g
  return true;
}

bool mpuRead(float &ax, float &ay, float &az, float &gx, float &gy, float &gz) {
  Wire.beginTransmission(mpuAddr);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(mpuAddr, (uint8_t)14) != 14) return false;
  int16_t raw[7];
  for (int i = 0; i < 7; i++) {
    uint8_t hi = Wire.read();
    uint8_t lo = Wire.read();
    raw[i] = (int16_t)((hi << 8) | lo);
  }
  if (raw[0] == 0 && raw[1] == 0 && raw[2] == 0) {   // chip reset itself -> wake it again
    mpuWrite(0x6B, 0x00);
    return false;
  }
  
  ax = raw[0] / 4096.0 * 9.80665;
  ay = raw[1] / 4096.0 * 9.80665;
  az = raw[2] / 4096.0 * 9.80665;
  gx = raw[4] / 131.0;
  gy = raw[5] / 131.0;
  gz = raw[6] / 131.0;
  return true;
}

void scanI2C() {
  Serial.print("I2C devices found:");
  int n = 0;
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) { Serial.printf(" 0x%02X", a); n++; }
  }
  Serial.println(n ? "" : " none");
}

DHT dht(PIN_DHT, DHTTYPE);

const byte ROWS = 4, COLS = 4;
char keys[ROWS][COLS] = {
  {'1','2','3','A'},
  {'4','5','6','B'},
  {'7','8','9','C'},
  {'*','0','#','D'}
};
byte rowPins[ROWS] = {19, 18, 5, 17};
byte colPins[COLS] = {16, 23, 32, 33};
Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);

struct Question { const char* text; const char* key; bool scale; };
Question questions[5] = {
  {"Are you injured?",                 "injured",                   false},
  {"Can you move on your own?",        "can_move",                  false},
  {"How many people are with you?",    "people_with_you",           true },
  {"Is it hard to breathe?",           "hard_to_breathe",           false},
  {"Do you need water or medication?", "needs_water_or_medication", false},
};
int answers[5];
int qIndex = 0;

enum State { POD_IDLE, POD_SURVEY, POD_DONE };
State state = POD_IDLE;
unsigned long doneAt = 0;
int caseCounter = 0;

struct Readings {
  bool  motion;
  int   soundLevel;
  bool  loud;
  bool  irObject;
  float tempC;
  float humidity;
  float accelMag;
  bool  tipped;
  bool  impact;
  float ax, ay, az;
  float gx, gy, gz;
};
Readings latest;
bool mpuOk = false;
int  soundMin = 4095, soundMax = 0;
float cachedTemp = NAN, cachedHum = NAN;
unsigned long lastDht = 0, lastTelemetry = 0;
bool lastMotion = false;
bool motionLatch = false;
float peakAccel = 0;
const float IMPACT_THRESHOLD = 12.0;

void beep(int ms) {
  digitalWrite(PIN_BUZZER, HIGH);
  delay(ms);
  digitalWrite(PIN_BUZZER, LOW);
}

void sampleSound() {
  int v = analogRead(PIN_SOUND);
  if (v < soundMin) soundMin = v;
  if (v > soundMax) soundMax = v;
}

void readSensors() {
  latest.motion   = motionLatch || digitalRead(PIN_PIR) == HIGH;
  motionLatch = false;
  latest.irObject = digitalRead(PIN_IR) == LOW;

  latest.soundLevel = (soundMax > soundMin) ? soundMax - soundMin : 0;
  latest.loud = latest.soundLevel > LOUD_THRESHOLD;
  soundMin = 4095; soundMax = 0;

  if (millis() - lastDht > 2000) {
    float t = dht.readTemperature();
    float h = dht.readHumidity();
    if (!isnan(t)) cachedTemp = t;
    if (!isnan(h)) cachedHum = h;
    lastDht = millis();
  }
  latest.tempC = cachedTemp;
  latest.humidity = cachedHum;

  if (mpuOk && mpuRead(latest.ax, latest.ay, latest.az, latest.gx, latest.gy, latest.gz)) {
    latest.accelMag = sqrt(latest.ax*latest.ax + latest.ay*latest.ay + latest.az*latest.az);
    latest.tipped = latest.az < 4.0;
    latest.impact = peakAccel > IMPACT_THRESHOLD;
  } else {
    latest.ax = latest.ay = latest.az = 0;
    latest.gx = latest.gy = latest.gz = 0;
    latest.accelMag = 0;
    latest.tipped = false;
    latest.impact = false;
  }
  peakAccel = 0;
}

void addReadings(JsonObject s) {
  s["motion_detected"] = latest.motion;
  s["sound_level"]     = latest.soundLevel;
  s["loud_sound"]      = latest.loud;
  s["object_close_ir"] = latest.irObject;
  if (isnan(latest.tempC)) s["temp_c"] = nullptr; else s["temp_c"] = latest.tempC;
  if (isnan(latest.humidity)) s["humidity"] = nullptr; else s["humidity"] = latest.humidity;
  s["accel_mag"]       = latest.accelMag;
  s["robot_tipped"]    = latest.tipped;
  s["impact"]          = latest.impact;
  JsonObject acc = s["accel"].to<JsonObject>();
  acc["x"] = latest.ax; acc["y"] = latest.ay; acc["z"] = latest.az;
  JsonObject gyr = s["gyro_dps"].to<JsonObject>();
  gyr["x"] = latest.gx; gyr["y"] = latest.gy; gyr["z"] = latest.gz;
}

bool postJson(const char* path, JsonDocument& doc) {
  if (WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  String url = String(SERVER) + path;
  WiFiClientSecure secureClient;
  WiFiClient plainClient;
  if (url.startsWith("https")) {
    secureClient.setInsecure();
    http.begin(secureClient, url);
  } else {
    http.begin(plainClient, url);
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Reach-Source", "hardware");          // backend tags records as hardware
  http.addHeader("ngrok-skip-browser-warning", "1");      // avoid ngrok's interstitial page
  http.setTimeout(3000);
  String body;
  serializeJson(doc, body);
  int code = http.POST(body);
  http.end();
  Serial.printf("POST %s -> %d\n", path, code);
  return code >= 200 && code < 300;
}

// POST /api/telemetry — flat payload matching the backend's TelemetryIn schema.
// Fields this pod cannot measure are omitted (location: no GPS; water_detected: no sensor),
// and the IMU is omitted when the MPU6050 is missing, so nothing is reported as a fake zero.
void sendTelemetry() {
  JsonDocument doc;
  doc["robot_id"]           = UNIT_ID;
  doc["sector"]             = SECTOR;
  doc["location_zone"]      = ZONE;
  doc["motion_detected"]    = latest.motion;
  // NOTE: this is the IR *proximity* sensor ("object close"), not a thermal/body-heat sensor.
  doc["infrared_triggered"] = latest.irObject;
  if (isnan(latest.tempC)) doc["temperature_c"] = nullptr;
  else                     doc["temperature_c"] = latest.tempC;
  if (mpuOk) {
    JsonObject acc = doc["accelerometer"].to<JsonObject>();
    acc["x"] = latest.ax; acc["y"] = latest.ay; acc["z"] = latest.az;
    JsonObject gyr = doc["gyroscope"].to<JsonObject>();
    gyr["x"] = latest.gx; gyr["y"] = latest.gy; gyr["z"] = latest.gz;
  }
  postJson("/api/telemetry", doc);
}

static const char* yesNo(bool v) { return v ? "yes" : "no"; }

// POST /api/surveys — maps the pod's five OLED questions onto the backend's SurveyAnswers
// ("yes" / "no"; the backend keeps anything unsent as "unknown").
bool sendCase() {
  JsonDocument doc;
  caseCounter++;
  doc["robot_id"] = UNIT_ID;
  doc["sector"]   = SECTOR;
  JsonObject ans = doc["answers"].to<JsonObject>();
  ans["injured"]              = yesNo(answers[0] == 1);  // "Are you injured?"
  ans["trapped"]              = yesNo(answers[1] != 1);  // "Can you move on your own?" (inverted)
  ans["others_present"]       = yesNo(answers[2] > 0);   // "How many people are with you?" (count > 0)
  ans["breathing_difficulty"] = yesNo(answers[3] == 1);  // "Is it hard to breathe?"
  ans["immediate_help"]       = yesNo(answers[4] == 1);  // "Do you need water or medication?" (closest match)
  return postJson("/api/surveys", doc);
}

void showIdle() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println(WiFi.status() == WL_CONNECTED ? "RESCUE POD  [online]" : "RESCUE POD  [offline]");
  display.printf("Motion:%s  IR:%s\n", latest.motion ? "YES" : "no", latest.irObject ? "YES" : "no");
  display.printf("Sound:%d %s\n", latest.soundLevel, latest.loud ? "LOUD" : "");
  if (isnan(latest.tempC)) display.println("Temp: --");
  else display.printf("Temp:%.1fC Hum:%.0f%%\n", latest.tempC, latest.humidity);
  display.printf("Tipped:%s Bump:%s\n", latest.tipped ? "YES" : "no", latest.impact ? "YES" : "no");
  display.println();
  display.println(latest.motion ? ">> Person detected!" : "");
  display.println("Press A for survey");
  display.display();
}

void showQuestion(int i) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.printf("Question %d of 5\n\n", i + 1);
  display.println(questions[i].text);
  display.println();
  display.println(questions[i].scale ? "Press a number 0-9" : "1 = Yes    2 = No");
  display.println("* = cancel");
  display.display();
}

void showMessage(const char* line1, const char* line2) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(0, 16);
  display.println(line1);
  display.println();
  display.println(line2);
  display.display();
}

void handleSurveyKey(char k) {
  if (k == '*') { state = POD_IDLE; return; }
  Question& q = questions[qIndex];
  int val = -1;
    if (q.scale && k >= '0' && k <= '9') val = k - '0';
  if (!q.scale && (k == '1' || k == '2')) val = (k == '1') ? 1 : 0;
  if (val < 0) return;

  answers[qIndex] = val;
  beep(40);
  qIndex++;
  if (qIndex < 5) {
    showQuestion(qIndex);
  } else {
    showMessage("Sending...", "");
    readSensors();
    bool ok = sendCase();
    showMessage(ok ? "Help is on the way." : "Saved - will retry.",
                ok ? "Stay where you are." : "Check WiFi/server.");
    state = POD_DONE;
    doneAt = millis();
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_PIR, INPUT);
  pinMode(PIN_IR, INPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
  analogReadResolution(12);

  Wire.begin(21, 22);
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) Serial.println("OLED not found");
  display.setTextColor(SSD1306_WHITE);
  showMessage("Rescue Pod booting", "Connecting WiFi...");

  scanI2C();   // OLED should show as 0x3C, MPU as 0x68
  mpuOk = mpuInit();
  if (!mpuOk) Serial.println("MPU6050 not found - continuing without it");
  dht.begin();

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 10000) delay(250);
  Serial.println(WiFi.status() == WL_CONNECTED ? "WiFi OK: " + WiFi.localIP().toString()
                                               : String("WiFi failed - running offline"));
  beep(100);
}

void loop() {
  sampleSound();
  if (digitalRead(PIN_PIR) == HIGH) motionLatch = true;
  if (mpuOk) {
    float ax, ay, az, gx, gy, gz;
    if (mpuRead(ax, ay, az, gx, gy, gz)) {
      float m = sqrt(ax*ax + ay*ay + az*az);
      if (m > peakAccel) peakAccel = m;
    }
  }
  char k = keypad.getKey();

  if (state == POD_IDLE) {
    if (millis() - lastTelemetry > TELEMETRY_MS) {
      readSensors();
      if (latest.motion && !lastMotion) beep(150);
      lastMotion = latest.motion;
      sendTelemetry();
      showIdle();
      lastTelemetry = millis();
    }
    if (k == 'A') {
      state = POD_SURVEY;
      qIndex = 0;
      beep(80);
      showQuestion(0);
    }
  } else if (state == POD_SURVEY) {
    if (k) handleSurveyKey(k);
  } else if (state == POD_DONE) {
    if (millis() - doneAt > 5000) state = POD_IDLE;
  }
}