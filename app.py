import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from ortools.sat.python import cp_model

app = Flask(__name__)
# تفعيل CORS للسماح لFirebase بالاتصال بالسيرفر
CORS(app, origins=["*"]) 

def solve_school_timetable(data):
    lessons = data.get("lessons", [])
    timeslots = data.get("timeslots", [])
    rooms = data.get("rooms", ["Default"])

    if not lessons or not timeslots:
        raise ValueError("Lessons and timeslots are required")

    model = cp_model.CpModel()
    assignments = {}

    # إنشاء المتغيرات
    for lesson in lessons:
        for t_idx in range(len(timeslots)):
            for r_idx in range(len(rooms)):
                assignments[(lesson["id"], t_idx, r_idx)] = model.NewBoolVar(
                    f'assign_{lesson["id"]}_t{t_idx}_r{r_idx}'
                )

    # قيد: كل درس يجب أن يوضع في حصة واحدة فقط
    for lesson in lessons:
        model.Add(
            sum(assignments[(lesson["id"], t_idx, r_idx)]
                for t_idx in range(len(timeslots))
                for r_idx in range(len(rooms))) == 1
        )

    # قيد: المعلم لا يدرس حصتين في نفس الوقت
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

    # قيد: الفصل لا يحصل على حصتين في نفس الوقت
    class_lessons = {}
    for lesson in lessons:
        class_id = lesson.get("classId")
        class_lessons.setdefault(class_id, []).append(lesson)
    
    for c_id, c_lessons in class_lessons.items():
        for t_idx in range(len(timeslots)):
            model.Add(
                sum(assignments[(lesson["id"], t_idx, r_idx)]
                    for lesson in c_lessons
                    for r_idx in range(len(rooms))) <= 1
            )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60.0 # تقليل الوقت لسرعة الاستجابة
    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        solution = []
        for lesson in lessons:
            for t_idx, timeslot in enumerate(timeslots):
                for r_idx, room in enumerate(rooms):
                    if solver.Value(assignments[(lesson["id"], t_idx, r_idx)]) == 1:
                        solution.append({
                            "lessonId": lesson["id"],
                            "subject": lesson["subject"],
                            "teacher": lesson["teacher"],
                            "classId": lesson["classId"],
                            "timeslot": timeslot # "الأحد_1"
                        })
        return solution
    else:
        raise Exception("لا يمكن إيجاد حل يحقق جميع الشروط")

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
