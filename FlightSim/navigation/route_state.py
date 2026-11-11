"""State file for Ollama-generated waypoints, shared within the simulator process.
For use in ui for plotting
Use `from navigation.route_state import route_waypoints` in another file.
It is empty before planning, while a new request runs, and after a failed request.
"""

route_waypoints = []
