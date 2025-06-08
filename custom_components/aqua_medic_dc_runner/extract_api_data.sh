#!/bin/bash

# Aqua Medic DC Runner - API Data Extraction Script (Fixed)
# This script captures network traffic while you use the Aqua Medic app to extract API credentials

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAPTURE_FILE="${SCRIPT_DIR}/api_capture.pcap"
CONFIG_FILE="${SCRIPT_DIR}/api_config.json"


echo "🔧 Aqua Medic DC Runner - API Data Extraction"
echo "=============================================="
echo
echo "This script will capture network traffic to extract API credentials from the Aqua Medic app."
echo

# Check if running as root for tcpdump
if [[ $EUID -eq 0 ]]; then
    echo "❌ Please run this script as a normal user (not sudo)"
    echo "   The script will ask for sudo password when needed."
    exit 1
fi

# Find network interface
echo "🔍 Finding network interface..."
INTERFACE=$(route get default | grep interface | awk '{print $2}')
if [[ -z "$INTERFACE" ]]; then
    echo "❌ Could not determine network interface. Please specify manually:"
    echo "   Available interfaces:"
    ifconfig | grep -E '^[a-z]' | awk '{print "   - " $1}' | tr -d ':'
    echo
    read -p "Enter interface name (e.g., en0): " INTERFACE
fi

echo "📡 Using network interface: $INTERFACE"
echo

# Instructions for user
echo "📋 INSTRUCTIONS:"
echo "1. This script will start capturing network traffic"
echo "2. Open the Aqua Medic app on your device"
echo "3. Log in if needed"
echo "4. Turn the pump ON and OFF at least once"
echo "5. Change the pump speed at least once"
echo "6. Press ENTER here when done"
echo
read -p "🚀 Press ENTER to start capture (or Ctrl+C to cancel)..."

# Start packet capture
echo "🎯 Starting packet capture..."
echo "   Capturing traffic to: $CAPTURE_FILE"
echo "   You can now use the Aqua Medic app..."
echo

# Run tcpdump in background
sudo tcpdump -i "$INTERFACE" -w "$CAPTURE_FILE" \
    '(host euapi.gizwits.com or host gizwits.com or port 8883) and not icmp' &
TCPDUMP_PID=$!

# Wait for user to finish
echo "📱 Use the Aqua Medic app now, then press ENTER when done..."
read -p "✅ Press ENTER when you've finished using the app: "

# Stop capture
echo "🛑 Stopping packet capture..."
sudo kill $TCPDUMP_PID 2>/dev/null
sleep 2

# Check if capture file exists
if [[ ! -f "$CAPTURE_FILE" ]]; then
    echo "❌ Capture file not found. Please try again."
    exit 1
fi

echo "📊 Analyzing captured traffic..."

# Initialize variables
APP_ID=""
USER_TOKEN=""
DEVICE_ID=""
PRODUCT_KEY=""

# Extract App ID from HTTP headers
echo "🔍 Extracting App ID..."
APP_ID=$(tshark -r "$CAPTURE_FILE" -Y "http.request" -T fields -e tcp.payload 2>/dev/null | xxd -r -p 2>/dev/null | grep -o "x-gizwits-application-id: [a-f0-9]*" | head -1 | cut -d' ' -f2 2>/dev/null)

# Extract User Token from HTTP headers  
echo "🔍 Extracting User Token..."
USER_TOKEN=$(tshark -r "$CAPTURE_FILE" -Y "http.request" -T fields -e tcp.payload 2>/dev/null | xxd -r -p 2>/dev/null | grep -o "x-gizwits-user-token: [a-f0-9]*" | head -1 | cut -d' ' -f2 2>/dev/null)

# Extract Product Key from datapoint URL
echo "🔍 Extracting Product Key..."
PRODUCT_KEY=$(tshark -r "$CAPTURE_FILE" -Y "http.request" -T fields -e http.request.uri 2>/dev/null | grep -o "product_key=[a-f0-9]*" | head -1 | cut -d'=' -f2 2>/dev/null)

# Try to get Device ID using API call if we have App ID and Token
if [[ -n "$APP_ID" && -n "$USER_TOKEN" ]]; then
    echo "🔄 Fetching Device ID from API..."
    DEVICES_JSON=$(curl -s -X GET "https://euapi.gizwits.com/app/bindings" \
        -H "X-Gizwits-Application-Id: $APP_ID" \
        -H "X-Gizwits-User-token: $USER_TOKEN" 2>/dev/null)
    
    if [[ -n "$DEVICES_JSON" ]]; then
        # Extract device ID using Python JSON parsing
        if command -v python3 >/dev/null 2>&1; then
            DEVICE_ID=$(echo "$DEVICES_JSON" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if 'devices' in data and len(data['devices']) > 0:
        print(data['devices'][0]['did'])
except:
    pass
" 2>/dev/null)
        else
            # Fallback using grep and sed if Python3 not available
            DEVICE_ID=$(echo "$DEVICES_JSON" | grep -o '"did":"[^"]*"' | head -1 | sed 's/"did":"\([^"]*\)"/\1/')
        fi
        
        # Also extract product key if not found yet
        if [[ -z "$PRODUCT_KEY" ]]; then
            if command -v python3 >/dev/null 2>&1; then
                PRODUCT_KEY=$(echo "$DEVICES_JSON" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if 'devices' in data and len(data['devices']) > 0:
        print(data['devices'][0]['product_key'])
except:
    pass
" 2>/dev/null)
            else
                # Fallback using grep and sed
                PRODUCT_KEY=$(echo "$DEVICES_JSON" | grep -o '"product_key":"[^"]*"' | head -1 | sed 's/"product_key":"\([^"]*\)"/\1/')
            fi
        fi
    fi
fi

# Display results
echo
echo "🔍 EXTRACTED API DATA:"
echo "====================="
echo "App ID:       ${APP_ID:-❌ Not found}"
echo "User Token:   ${USER_TOKEN:-❌ Not found}"
echo "Device ID:    ${DEVICE_ID:-❌ Not found}"
echo "Product Key:  ${PRODUCT_KEY:-❌ Not found}"
echo

# Save to config file if we have the essential data
if [[ -n "$APP_ID" && -n "$USER_TOKEN" && -n "$DEVICE_ID" ]]; then
    cat > "$CONFIG_FILE" << EOF
{
  "app_id": "$APP_ID",
  "user_token": "$USER_TOKEN",
  "device_id": "$DEVICE_ID",
  "product_key": "$PRODUCT_KEY",
  "api_base_url": "https://euapi.gizwits.com"
}
EOF
    
    echo "✅ Configuration saved to: $CONFIG_FILE"
    echo
    echo "🏠 HOME ASSISTANT SETUP:"
    echo "========================"
    echo "Use these values in Home Assistant:"
    echo "- App ID: $APP_ID"
    echo "- User Token: $USER_TOKEN"
    echo "- Device ID: $DEVICE_ID"
    echo
    echo "🧪 TEST YOUR SETUP:"
    echo "==================="
    echo "curl -X POST \"https://euapi.gizwits.com/app/control/$DEVICE_ID\" \\"
    echo "  -H \"X-Gizwits-Application-Id: $APP_ID\" \\"
    echo "  -H \"X-Gizwits-User-token: $USER_TOKEN\" \\"
    echo "  -H \"Content-Type: application/json\" \\"
    echo "  -d '{\"attrs\": {\"SwitchON\": 1}}'"
    echo
else
    echo "❌ Could not extract all required data. Please try:"
    echo "1. Make sure you logged into the app during capture"
    echo "2. Make sure you controlled the pump (on/off/speed)"
    echo "3. Check that the app made HTTP requests (not just HTTPS)"
    echo "4. Run the script again"
fi

echo "📁 Files created:"
echo "- Packet capture: $CAPTURE_FILE"
if [[ -f "$CONFIG_FILE" ]]; then
    echo "- Configuration: $CONFIG_FILE"
fi
echo
echo "🗑️  To clean up: rm '$CAPTURE_FILE' '$CONFIG_FILE'"