import time
import rerun as rr

rr.init("rerun_example_serve_web_viewer", spawn=False)
# Start a gRPC server and use it as log sink.
server_uri = rr.serve_grpc()

print("Started grpc stream on", server_uri)
# Connect the web viewer to the gRPC server and open it in the browser
rr.serve_web_viewer(connect_to=server_uri, open_browser=False)

# logs = rr.serve_web(
#     web_port=9090,
#     grpc_port=9876,
#     open_browser=False
# )
# print (f"gRPC server listening on {logs}")
# Log some data to the gRPC server.
rr.log("data", rr.Boxes3D(half_sizes=[2.0, 2.0, 1.0]))

print("Go to http://172.22.2.1/?url=rerun%2Bhttp%3A%2F%2F172.22.1.2%3A9876%2Fproxy")
print("Or run rerun --connect rerun+http://172.22.1.2:9876/proxy in another terminal")

# Keep server running. If we cancel it too early, data may never arrive in the browser.
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nShutting down server…")