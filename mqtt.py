# Provides 4 lightweight functions to integrate MQTT data transfer
#
# Functions:
#   mqtt_connect(clientid)
#   create_publish_properties()
#   mqtt_quick_pub(client, publish_properties, data, file, topic)
#   mqtt_close(client)

import paho.mqtt.client as mqtt
import paho.mqtt.properties as props
from paho.mqtt.packettypes import PacketTypes


# Returns an MQTT client connected to the Mac Mini
# Params:
#   clientid - The name of the client seen by the broker. Can be any string.
# Note: This must be run before mqtt_quick_pub()
# Only contains two callback functions, on_log and on_connect
def mqtt_connect(clientid):
    broker = "10.147.18.165"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=clientid, protocol=mqtt.MQTTv5)
    client.username_pw_set("changlab", "electrode")

    client.connect(broker, 1883, 60)
    client.loop_start()

    return client


# Returns a properties object of packet type publish.
# Run this alongside mqtt_connect and pass as an argument to mqtt_quick_pub
def create_publish_properties():
    publish_properties = props.Properties(PacketTypes.PUBLISH)
    props.MaximumPacketSize = 20
    return publish_properties


# Lightweight publish function, best for small data samples that need to be published fast
# Params -
#   client - Client object connected to broker. Created by mqtt_connect
#   publish_properties - Properties object created by create_publish_properties. Only supports packet type publish.
#   data - The data to be transferred
#   file - Name of the file to store the data in
#   topic - Pathname the broker will use to send data to subscribers. Should be a string of form "/topic/"
def mqtt_quick_pub(client, publish_properties, data, key, file, topic):
    publish_properties.UserProperty = [
        ('File-Name', file),
        ('File-Size', str(len(data))),
        ('Key', key)]
    client.publish(topic, data, 0, False, properties=publish_properties)


# Stops the loop and disconnects client from broker
# Params -
#   client - client to disconnect
def mqtt_close(client):
    client.loop_stop()
    client.disconnect()
