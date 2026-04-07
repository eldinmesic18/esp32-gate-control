#include "esp_camera.h"
#include <WiFi.h>

// ==========================================
// KONFIGURATION (Bitte anpassen!)
// ==========================================
const char* ssid = "Galaxy S23 F3C3";
const char* password = "Eldin123";

// Wähle dein Kameramodell
// #define CAMERA_MODEL_WROVER_KIT // Has PSRAM
// #define CAMERA_MODEL_ESP_EYE // Has PSRAM
// #define CAMERA_MODEL_M5STACK_PSRAM // Has PSRAM
// #define CAMERA_MODEL_M5STACK_V2_PSRAM // M5Camera version B Has PSRAM
// #define CAMERA_MODEL_M5STACK_WIDE // Has PSRAM
// #define CAMERA_MODEL_M5STACK_ESP32CAM // No PSRAM
// #define CAMERA_MODEL_M5STACK_UNITCAM // No PSRAM
#define CAMERA_MODEL_AI_THINKER // Has PSRAM

// GPIO für das Relais
int RELAY_PIN = 14;
// Logik: HIGH oder LOW um Relais zu schalten?
// true = HIGH aktiviert, false = LOW aktiviert
bool RELAY_ACTIVE_HIGH = true; 

#include "camera_pins.h"

void startCameraServer();

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println();

  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, !RELAY_ACTIVE_HIGH); // Initial state: OFF

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 10000000;
  config.pixel_format = PIXFORMAT_JPEG;
  
  // if PSRAM IC present, init with UXGA resolution and higher JPEG quality
  //                      for larger pre-allocated frame buffer.
  if(psramFound()){
    config.frame_size = FRAMESIZE_UXGA;
    config.jpeg_quality = 10;
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_SVGA;
    config.jpeg_quality = 12;
    config.fb_count = 1;
  }

  // Camera init
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x", err);
    return;
  }

  // ===================================================
  // Sensor-Einstellungen für OV2640 (fixes black image)
  // ===================================================
  sensor_t * s = esp_camera_sensor_get();
  // Auto-Exposure & Auto-Gain aktivieren (kritisch für helles Bild)
  s->set_exposure_ctrl(s, 1);   // Auto-Exposure EIN
  s->set_gain_ctrl(s, 1);       // Auto-Gain EIN
  s->set_awb_gain(s, 1);        // Auto-White-Balance-Gain EIN
  s->set_whitebal(s, 1);        // White Balance EIN
  // Bild-Qualität & Helligkeit
  s->set_brightness(s, 1);      // Helligkeit: -2 bis 2 (0 = Standard)
  s->set_contrast(s, 0);        // Kontrast: -2 bis 2
  s->set_saturation(s, 0);      // Sättigung: -2 bis 2
  s->set_ae_level(s, 0);        // AE-Stufe: -2 bis 2
  // Linsenkorrektur & Rauschunterdrückung
  s->set_lenc(s, 1);            // Linsenkorrektur EIN
  s->set_raw_gma(s, 1);         // Gamma EIN
  s->set_bpc(s, 0);             // Black Pixel Correction AUS
  s->set_wpc(s, 1);             // White Pixel Correction EIN
  s->set_dcw(s, 1);             // Downsize EIN
  // Auflösung & Qualität für flüssiges Streaming
  s->set_framesize(s, FRAMESIZE_VGA); // 640x480 (flüssiger als UXGA)
  s->set_quality(s, 12);         // JPEG-Qualität: 0-63 (niedriger = besser)


  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.println("WiFi connected");

  startCameraServer();

  Serial.print("Camera Ready! Use 'http://");
  Serial.print(WiFi.localIP());
  Serial.println("' to connect");
}

void loop() {
  delay(10000);
}
