/*
 * =====================================================================================
 *  TACTICAL LORA MESH NODE 2 - "LORA SECOND MODULE"
 *  Firmware for ESP32 + LoRa (SX1276 / SX1278 / RFM95)
 * =====================================================================================
 *  Features:
 *  - Advertises via Bluetooth LE as "LORA SECOND MODULE" (Nordic UART Service)
 *  - Communicates over LoRa Radio (433.00 MHz, SF7, BW 125kHz, CR 4/5)
 *  - Transmits Sensor Telemetry (Temp, Humidity, Gas/Smoke, Water, GPS)
 *  - Relays Decentralized Mesh Chat, SOS Emergency Strobes & Shelter Waypoints
 * =====================================================================================
 */

#include <SPI.h>
#include <LoRa.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// ── LoRa Module Pin Definitions (ESP32 Standard SPI) ──────────────────────────
#define LORA_SCK     18
#define LORA_MISO    19
#define LORA_MOSI    23
#define LORA_CS      5     // NSS
#define LORA_RST     14    // RESET
#define LORA_DIO0    2     // IRQ (Interrupt pin)

// LoRa RF Parameters (Match Node 1 & Web HUD)
#define LORA_BAND    433E6 // 433 MHz (change to 868E6 or 915E6 if using that frequency)
#define LORA_SF      7     // Spreading Factor (SF7)
#define LORA_BW      125E3 // Bandwidth (125 kHz)
#define LORA_CR      5     // Coding Rate 4/5 (5)
#define LORA_TX_PWR  20    // 20 dBm (Max Tx Power)

// ── Node Identity ─────────────────────────────────────────────────────────────
#define NODE_NAME    "LORA SECOND MODULE"
#define NODE_CALLSIGN "NODE-2"

// ── Nordic UART Service (NUS) UUIDs ───────────────────────────────────────────
#define SERVICE_UUID           "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define CHARACTERISTIC_UUID_RX "6E400002-B5A3-F393-E0A9-E50E24DCCA9E" // App -> ESP32 (Write)
#define CHARACTERISTIC_UUID_TX "6E400003-B5A3-F393-E0A9-E50E24DCCA9E" // ESP32 -> App (Notify)

// ── Global Variables ──────────────────────────────────────────────────────────
BLEServer *pServer = NULL;
BLECharacteristic *pTxCharacteristic = NULL;
bool bleConnected = false;

// Mock / Sensor Readings for Node 2
float nodeLat = 13.0850;
float nodeLng = 80.2730;
float nodeTemp = 27.4;
float nodeHum = 61.2;
int nodeSmoke = 215;
int nodeWater = 490;

unsigned long lastTelemetryTx = 0;
const unsigned long TELEMETRY_INTERVAL_MS = 5000; // Send telemetry every 5s

// ── Function Declarations ─────────────────────────────────────────────────────
void sendLoRaPacket(String packet);
void notifyBLE(String msg);
void handleIncomingPacket(String packet, int rssi, float snr);

// ── BLE Callbacks ─────────────────────────────────────────────────────────────
class ServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) override {
      bleConnected = true;
      Serial.println("[BLE] Client Connected to LORA SECOND MODULE");
    }

    void onDisconnect(BLEServer* pServer) override {
      bleConnected = false;
      Serial.println("[BLE] Client Disconnected. Re-advertising...");
      BLEDevice::startAdvertising();
    }
};

class RxCallbacks: public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pCharacteristic) override {
      String rxValue = pCharacteristic->getValue().c_str();
      rxValue.trim();
      if (rxValue.length() > 0) {
        Serial.print("[BLE -> LoRa TX]: ");
        Serial.println(rxValue);
        // Broadcast packet over LoRa mesh
        sendLoRaPacket(rxValue);
      }
    }
};

// ── Setup ─────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=======================================================");
  Serial.println("  TACTICAL MESH NODE: " NODE_NAME " (" NODE_CALLSIGN ")");
  Serial.println("=======================================================");

  // 1. Initialize LoRa Radio
  Serial.println("[LORA] Initializing SX1276/78 transceiver...");
  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_CS);
  LoRa.setPins(LORA_CS, LORA_RST, LORA_DIO0);

  if (!LoRa.begin(LORA_BAND)) {
    Serial.println("[LORA ERROR] LoRa init failed! Check wiring & pins.");
  } else {
    LoRa.setSpreadingFactor(LORA_SF);
    LoRa.setSignalBandwidth(LORA_BW);
    LoRa.setCodingRate4(LORA_CR);
    LoRa.setTxPower(LORA_TX_PWR);
    LoRa.setSyncWord(0x12); // Tactical mesh sync word
    LoRa.enableCrc();
    Serial.println("[LORA] Radio initialized at 433.00 MHz (SF7 / BW125 / CR4:5)");
  }

  // 2. Initialize BLE
  Serial.println("[BLE] Starting BLE Stack as '" NODE_NAME "'...");
  BLEDevice::init(NODE_NAME);
  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new ServerCallbacks());

  BLEService *pService = pServer->createService(SERVICE_UUID);

  pTxCharacteristic = pService->createCharacteristic(
                        CHARACTERISTIC_UUID_TX,
                        BLECharacteristic::PROPERTY_NOTIFY
                      );
  pTxCharacteristic->addDescriptor(new BLE2902());

  BLECharacteristic *pRxCharacteristic = pService->createCharacteristic(
                                           CHARACTERISTIC_UUID_RX,
                                           BLECharacteristic::PROPERTY_WRITE
                                         );
  pRxCharacteristic->setCallbacks(new RxCallbacks());

  pService->start();

  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  pAdvertising->setMinPreferred(0x06);
  pAdvertising->setMinPreferred(0x12);
  BLEDevice::startAdvertising();

  Serial.println("[BLE] Advertising active as '" NODE_NAME "'. Ready for pairing!");
}

// ── Main Loop ─────────────────────────────────────────────────────────────────
void loop() {
  // 1. Check for incoming LoRa Packets
  int packetSize = LoRa.parsePacket();
  if (packetSize) {
    String incoming = "";
    while (LoRa.available()) {
      incoming += (char)LoRa.read();
    }
    int rssi = LoRa.packetRssi();
    float snr = LoRa.packetSnr();

    handleIncomingPacket(incoming, rssi, snr);
  }

  // 2. Periodically Broadcast Node 2 Sensor Telemetry over LoRa & BLE
  unsigned long now = millis();
  if (now - lastTelemetryTx >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryTx = now;

    // Small drift to simulate live sensor fluctuations
    nodeTemp += ((random(0, 10) - 5) * 0.05);
    nodeHum  += ((random(0, 10) - 5) * 0.1);
    nodeSmoke = constrain(nodeSmoke + random(-4, 5), 180, 450);
    nodeWater = constrain(nodeWater + random(-6, 7), 400, 650);

    // Format: SYS:lat,lng,temp,hum,smoke,water
    String telemetryPacket = "SYS:" + String(nodeLat, 5) + "," + String(nodeLng, 5) + "," +
                             String(nodeTemp, 1) + "," + String(nodeHum, 1) + "," +
                             String(nodeSmoke) + "," + String(nodeWater);

    Serial.print("[NODE-2 TELEMETRY]: ");
    Serial.println(telemetryPacket);

    // Broadcast over LoRa radio to other nodes & gateway
    sendLoRaPacket(telemetryPacket);

    // If a phone/PC is connected to Node 2 via BLE, notify it directly
    if (bleConnected) {
      notifyBLE(telemetryPacket);
    }
  }

  delay(20);
}

// ── LoRa Transmit ─────────────────────────────────────────────────────────────
void sendLoRaPacket(String packet) {
  LoRa.beginPacket();
  LoRa.print(packet);
  LoRa.endPacket();
  Serial.println("[LoRa TX -> Mesh] " + packet);
}

// ── BLE Notify ────────────────────────────────────────────────────────────────
void notifyBLE(String msg) {
  if (pTxCharacteristic && bleConnected) {
    msg += "\n";
    pTxCharacteristic->setValue(msg.c_str());
    pTxCharacteristic->notify();
  }
}

// ── LoRa Packet Handling ──────────────────────────────────────────────────────
void handleIncomingPacket(String packet, int rssi, float snr) {
  packet.trim();
  Serial.print("[LoRa RX <- Mesh] (RSSI: ");
  Serial.print(rssi);
  Serial.print(" dBm, SNR: ");
  Serial.print(snr);
  Serial.print(" dB): ");
  Serial.println(packet);

  // If connected via BLE, forward mesh packet to connected device
  if (bleConnected) {
    notifyBLE(packet);
  }

  // Parse packet type
  if (packet.startsWith("CHAT:")) {
    Serial.println("[COMM] Chat received over LoRa mesh");
  } else if (packet.startsWith("SOS:")) {
    Serial.println("[EMERGENCY] !!! SOS EMERGENCY PACKET RECEIVED ON NODE 2 !!!");
    // Trigger local buzzer / LED strobe if installed on Node 2
  } else if (packet.startsWith("WAYPOINT:")) {
    Serial.println("[TACTICAL] New waypoint / shelter broadcasted");
  }
}
