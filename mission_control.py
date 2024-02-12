##Author:
##Date Started:
##Notes: Control experiment from here.
##pithytimeout=0

from time import sleep, time
from database import Database
import pulse
import json
import test_ender as pr

##############################

EXP_ID = '20240206_WC_JE_EFC_1M_H2SO4_delay=11_dur=3_test4'


##############################

def main():
    database = Database(db_filename=EXP_ID)
    fn = "files/ultrasound/" + EXP_ID + ".json"
    start_time = time()
    current_time = time()
    stepz = 0
    stepy = 0

    while current_time - start_time < 24. * 3600:
        try:
            print('pulsing')
            waveform: dict[str, list[float]] = pulse.pulse()
            other_fields: dict[str, float] = {'time': time()}
            waveform.update(other_fields)

            with open(fn, 'a') as file:
                json.dump(waveform, file)
                file.write('\n')  # Add a newline character after each JSON object

            query: str = database.parse_query(payload=waveform)
            # print(query)
            row_id: int = database.write(query)
            # print('\trow id:', row_id)

            sleep(2.)
            # if stepy == 80: #if end of y-axis
            #     pr.send_command("G1 Y-40.0 \r\n")
            #     stepz = stepz + 1
            #     if stepz <= 30: #before end of z-axis
            #         pr.send_command("G1 Z-0.5 \r\n")
            #         print(stepy,stepz)
            #         stepy = 0
            #         sleep(0.5)
            #     else: #if end of z-axis
            #         print(stepy,stepz)
            #         stepy = 0
            #         sleep(0.5)
            #         pr.send_command("G1 Z15.0 \r\n")
            #         sleep(0.5)
            #         stepz = 0
            #         break
            # else: #increment y
            #     pr.send_command("G1 Y0.5 \r\n")
            #     stepy = stepy + 1

            # current_time = time()

        except Exception as e:
            print(e)


if __name__ == '__main__':
    main()
