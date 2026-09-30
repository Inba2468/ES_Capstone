/*
 * =====================================================================================
 *  TACTICAL LORA MESH NODE 1 - GATEWAY / PRIMARY NODE
 *  Firmware for ESP32 + LoRa (SX1276 / SX1278 / RFM95)
 * =====================================================================================
 *  Features:
 *  - Advertises via Bluetooth LE as "ESP32-LoRa-Node" (Nordic UART Service)
 *  - Communicates over LoRa Radio (433.00 MHz, SF7, BW 125kHz, CR 4/5)
 *  - Relays packets bidirectionally between Web HUD and LoRa Mesh
 * =====================================================================================
 */

#include <SPI.h>
#include <LoRa.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

#define LORA_SCK     18
#define LORA_MISO    19
#define LORA_MOSI    23
#define LORA_CS      5
#define LORA_RST     14
#define LORA_DIO0    2

#define LORA_BAND    433E6
#define LORA_SF      7
#define LORA_BW      125E3
#define LORA_CR      5
#define LORA_TX_PWR  20

#define NODE_NAME    "ESP32-LoRa-Node"
#define NODE_CALLSIGN "GATEWAY"

#define SERVICE_UUID           "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define CHARACTERISTIC_UUID_RX "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
#define CHARACTERISTIC_UUID_TX "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

BLEServer *pServer = NULL;
BLECharacteristic *pTxCharacteristic = NULL;
bool bleConnected = false;

float nodeLat = 13.0827;
float nodeLng = 80.2707;
float nodeTemp = 28.0;
float nodeHum = 65.0;
int nodeSmoke = 240;
int nodeWater = 520;

unsigned long lastTelemetryTx = 0;
const unsigned long TELEMETRY_INTERVAL_MS = 4000;

void sendLoRaPacket(String packet);
void notifyBLE(String msg);
void handleIncomingPacket(String packet, int rssi, float snr);

class ServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) override {
      bleConnected = true;
      Serial.println("[BLE] Client Connected to GATEWAY");
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
        sendLoRaPacket(rxValue);
      }
    }
};

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=======================================================");
  Serial.println("  TACTICAL MESH NODE: " NODE_NAME " (" NODE_CALLSIGN ")");
  Serial.println("=======================================================");

  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_CS);
  LoRa.setPins(LORA_CS, LORA_RST, LORA_DIO0);

  if (!LoRa.begin(LORA_BAND)) {
    Serial.println("[LORA ERROR] LoRa init failed! Check wiring & pins.");
  } else {
    LoRa.setSpreadingFactor(LORA_SF);
    LoRa.setSignalBandwidth(LORA_BW);
    LoRa.setCodingRate4(LORA_CR);
    LoRa.setTxPower(LORA_TX_PWR);
    LoRa.setSyncWord(0x12);
    LoRa.enableCrc();
    Serial.println("[LORA] Radio initialized at 433.00 MHz");
  }

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

  Serial.println("[BLE] Advertising active as '" NODE_NAME "'.");
}

void loop() {
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

  unsigned long now = millis();
  if (now - lastTelemetryTx >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryTx = now;
    String telemetryPacket = "SYS:" + String(nodeLat, 5) + "," + String(nodeLng, 5) + "," +
                             String(nodeTemp, 1) + "," + String(nodeHum, 1) + "," +
                             String(nodeSmoke) + "," + String(nodeWater);

    sendLoRaPacket(telemetryPacket);
    if (bleConnected) {
      notifyBLE(telemetryPacket);
    }
  }

  delay(20);
}

void sendLoRaPacket(String packet) {
  LoRa.beginPacket();
  LoRa.print(packet);
  LoRa.endPacket();
  Serial.println("[LoRa TX -> Mesh] " + packet);
}

void notifyBLE(String msg) {
  if (pTxCharacteristic && bleConnected) {
    msg += "\n";
    pTxCharacteristic->setValue(msg.c_str());
    pTxCharacteristic->notify();
  }
}

void handleIncomingPacket(String packet, int rssi, float snr) {
  packet.trim();
  Serial.print("[LoRa RX <- Mesh] (RSSI: " + String(rssi) + " dBm): ");
  Serial.println(packet);

  if (bleConnected) {
    notifyBLE(packet);
  }
}
