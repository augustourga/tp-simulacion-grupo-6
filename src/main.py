import random
from scipy import stats
from collections import deque 

HV = float('inf')

PENALIZATION_TIME = 20  # ms
RESPONSE_TIME_THRESHOLD = 500 # ms
CANCELLATION_PROBABILITY = 0.20

class Simulation:
    def __init__(self, cw, tmcpu, tf):
        self.CW = cw  
        self.TMCPU = tmcpu  
        self.TF = tf * 60 * 60 * 1000  # from hours to milliseconds

        self.T = 0
        self.TPLL = 0
        self.STLL = 0
        self.STOC = 0
        self.STS = 0
        self.STE = 0
        self.NT = 0
        self.CP = 0
        self.CRS = 0
        self.LOST_REQUESTS = 0

        self.TPS = [HV] * cw
        self.ITO = [0.0] * cw
        self.CIR = [0.0] * cw 
        self.SERV = [0.0] * cw 
        self.UCPU = [0.0] * cw

        self.ASSIGNED_REQUEST_ARRIVAL_TIME = [0.0] * cw 
        self.ARRIVAL_QUEUE = deque() 


    def generate_interarrival_time(self):
        loc = 0.0
        scale = 74.34144
        return stats.expon.rvs(loc=loc, scale=scale, size=1)[0]

    def generate_service_time(self):
        h = 1.0007386965056315
        k = 1.0003493448869198
        loc = 0.6312614866274571
        scale = 499.5433767462339
        return stats.kappa4.rvs(h, k, loc=loc, scale=scale, size=1)[0]  # in ms

    def generate_cpu_usage(self):
        a = 2524468.3663236685
        loc = -4699.859387148292
        scale = 0.001885497347450249
        return stats.erlang.rvs(a=a, loc=loc, scale=scale, size=25000)[0]

    def find_next_departure_index(self):
        min_time = min(self.TPS)
        return self.TPS.index(min_time)

    def find_idle_worker(self):
        max_time = max(self.TPS)
        return self.TPS.index(max_time)

    def assign_new_task_to_worker(self, i):
        self.CIR[i] = self.generate_cpu_usage()
        self.SERV[i] = self.generate_service_time()
        self.UCPU[i] = self.CIR[i]
        
        self.ASSIGNED_REQUEST_ARRIVAL_TIME[i] = self.ARRIVAL_QUEUE.popleft() 


        total_cpu_usage = sum(self.UCPU)

        if total_cpu_usage <= self.TMCPU:
            self.TPS[i] = self.T + self.SERV[i]
            self.STE += self.SERV[i]
            print(f"[ASSIGN] Time={self.T}ms | Worker={i} | CPU OK | SERV={self.SERV[i]:.2f}ms")
        else:
            self.TPS[i] = self.T + self.SERV[i] + PENALIZATION_TIME
            self.STE += self.SERV[i] + PENALIZATION_TIME
            self.CP += 1
            print(f"[ASSIGN] Time={self.T}ms | Worker={i} | CPU EXCEEDED | SERV+PEN={self.SERV[i] + PENALIZATION_TIME:.2f}ms")

    def run(self):
        while True:
            i = self.find_next_departure_index()

            if self.TPLL < self.TPS[i]:
                self.T = self.TPLL
                self.STLL += self.T
                self.NT += 1
                self.CRS += 1
                self.TPLL = self.T + self.generate_interarrival_time()
                
                self.ARRIVAL_QUEUE.append(self.T) 

                print(f"[ARRIVAL] Time={self.T}ms | CRS={self.CRS} | NT={self.NT} , TPLL= {self.TPLL} , TPS[{i}] = {self.TPS[i]}")

                if self.CRS <= self.CW:
                    index = self.find_idle_worker()
                    self.STOC += self.T - self.ITO[index]
                    self.assign_new_task_to_worker(index)
            else:
                if self.CRS > 0:
                    self.T = self.TPS[i]
                    self.STS += self.T
                    self.CRS -= 1
                    
                    response_time = self.T - self.ASSIGNED_REQUEST_ARRIVAL_TIME[i] 

                    if response_time > RESPONSE_TIME_THRESHOLD:
                        if random.random() < CANCELLATION_PROBABILITY:
                            self.LOST_REQUESTS += 1
                            print(f"[DEPARTURE] Time={self.T}ms | Worker={i} | CRS={self.CRS} | LOST (Total Response Time: {response_time:.2f}ms)")
                        else:
                            print(f"[DEPARTURE] Time={self.T}ms | Worker={i} | CRS={self.CRS} | Total Response Time: {response_time:.2f}ms")
                    else:
                        print(f"[DEPARTURE] Time={self.T}ms | Worker={i} | CRS={self.CRS} | Total Response Time: {response_time:.2f}ms")

                    self.UCPU[i] = 0.0

                    if self.CRS >= self.CW:
                        if self.ARRIVAL_QUEUE: 
                            self.assign_new_task_to_worker(i)
                        else:
                            self.TPS[i] = HV
                            self.ITO[i] = self.T
                            self.ASSIGNED_REQUEST_ARRIVAL_TIME[i] = 0.0
                    else:
                        self.TPS[i] = HV
                        self.ITO[i] = self.T
                        self.ASSIGNED_REQUEST_ARRIVAL_TIME[i] = 0.0


            if self.T > self.TF:
                self.TPLL = HV
                if self.CRS == 0 and not self.ARRIVAL_QUEUE: 
                    print("[END] Simulation time exceeded and system is empty.")
                    break

        return self.calculate_statistics()

    def calculate_statistics(self):
        TPER = (self.STS - self.STLL - self.STE) / self.NT if self.NT else 0 
        PPCMCPU = self.CP / self.NT if self.NT else 0
        PTO = (self.STOC * 100) / (self.T * self.CW) if self.T else 0
        PPP = (self.LOST_REQUESTS / self.NT) * 100 if self.NT else 0 
        return {
            "TPER (ms)": TPER, 
            "PPCMCPU": PPCMCPU,
            "PTO (%)": PTO,
            "PPP (%)": PPP
        }


if __name__ == "__main__":
    print("=== SIMULATION CONFIGURATION ===")
    CW = int(input("Enter CW (Max concurrent CPU jobs) [units: workers]: "))
    TMCPU = float(input("Enter TMCPU (Max CPU usage before penalty) [units: MIPS]: "))
    TF = float(input("Enter TF (Simulation end time) [units: hours]: "))

    sim = Simulation(CW, TMCPU, TF)
    results = sim.run()

    print("\n=== SIMULATION RESULTS ===")
    print(f"Average queue time (TPER): {results['TPER (ms)']:.2f} ms")
    print(f"Penalty rate (PPCMCPU): {results['PPCMCPU']:.2%}")
    print(f"CPU idle percentage (PTO): {results['PTO (%)']:.2f}%")
    print(f"Lost Requests Percentage (PPP): {results['PPP (%)']:.2f}%")