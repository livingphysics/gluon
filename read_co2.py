from atlas_i2c import atlas_i2c, sensors, commands
sensor_co2 = sensors.Sensor("CO2",105)
sensor_co2.connect()
sensor_o2 = sensors.Sensor("O2",108)
sensor_o2.connect()
while True:
	co2_reading = sensor_co2.query(commands.READ)
	o2_reading = sensor_o2.query(commands.READ)
	print("CO2:"+co2_reading.data.decode()+"ppm O2:"+	o2_reading.data.decode()+"%")

# sensor_address=105
# dev = atlas_i2c.AtlasI2C()
# dev.set_i2c_address(sensor_address)
# dev.set_i2c_address(sensor_address)

# while True:
	# result = dev.query("R",processing_delay=1500)
	# print(result.data)

	
