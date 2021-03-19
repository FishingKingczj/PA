import sys
import simulator

if len(sys.argv) < 2:
    print("no trace file name")
    exit(0)

file = open(sys.argv[1])
if len(sys.argv) == 3 and sys.argv[2] == "o":
    simulator.init_simulator(True)
else:
    simulator.init_simulator(False)

for line in file:
    if line.strip() == "":
        continue
    param = line.strip().split(" ")
    if len(param) == 1:
        # output command
        if param[0] == "v":
            simulator.output_v()
        if param[0] == "h":
            simulator.output_h()
        if param[0] == "p":
            simulator.output_p()
    elif len(param) == 3:
        processor = int(param[0][1])
        operation = param[1]
        address = int(param[2])
        simulator.run_operation(processor, operation, address)
    else:
        print("command error: %s" % line)
        exit(0)
file.close()
file = open("out_" + sys.argv[1], "w")
file.write(simulator.report_statics())
file.close()

print("simulation finished, enter to exit")
input()