from obspy.clients.fdsn import Client
from obspy import UTCDateTime

client = Client("RASPISHAKE")

network = "AM"
station = "RD4DD"
location = "00"
channel = "*"

end = UTCDateTime() - 120
start = end - 5

print("Fetching waveform...")

st = client.get_waveforms(
    network,
    station,
    location,
    channel,
    start,
    end
)

print(st)
print("Samples:", len(st[0].data))
print("Sampling rate:", st[0].stats.sampling_rate)