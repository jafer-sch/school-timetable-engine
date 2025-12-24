import os
from flask import Flask, request, jsonify
from ortools.sat.python import cp_model

app = Flask(__name__)

def solve_school_timetable(data):
    lessons = data.get("lessons", [])
    timeslots = data.get("timeslots", [])
    rooms = data.get("rooms", ["Default"])

    if not lessons or not timeslots:
        raise ValueError("Lessons and timeslots are required")

    model = cp_model.CpModel()

    assignments = {}
    for lesson in lessons:
        for t_idx, _ in enumerate(timeslots):
            for r_idx, _ in enumerate(rooms):
                assignments[(lesson["id"], t_idx, r_idx)] = model.NewBoolVar(
                    f'assign_{lesson["id"]}_t{t_idx}_r{r_idx}'
                )

    for lesson in lessons:
        model.Add(
            sum(assignments[(lesson["id"], t_idx, r_idx)]
                for t_idx in range(len(timeslots))
                for r_idx in range(len(rooms))) == 1
        )

    teacher_lessons = {}
    for lesson in lessons:
        teacher = lesson["teacher"]
        teacher_lessons.setdefault(teacher, []).append(lesson)

    for teacher, t_lessons in teacher_lessons.items():
        for t_idx in range(len(timeslots)):
            model.Add(
                sum(assignments[(lesson["id"], t_idx, r_idx)]
                    for lesson in t_lessons
                    for r_idx in range(len(rooms))) <= 1
            )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 300.0
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        solution = {}
        for lesson in lessons:
            for t_idx, timeslot in enumerate(timeslots):
                for r_idx, room in enumerate(rooms):
                    if solver.Value(assignments[(lesson["id"], t_idx, r_idx)]) == 1:
                        solution[lesson["id"]] = {
                            "lesson": lesson,
                            "assigned_timeslot": timeslot,
                            "assigned_room": room
                        }
        return solution
    else:
        raise Exception("No feasible timetable could be generated within time limit")

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "OK"})

@app.route('/solve', methods=['POST'])
def solve():
    try:
        input_data = request.json
        result = solve_school_timetable(input_data)
        return jsonify({"status": "success", "timetable": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
