import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from ortools.sat.python import cp_model

app = Flask(__name__)
# تفعيل CORS للسماح بالاتصال من واجهة الويب الخاصة بك
CORS(app, origins=["https://schooj-efd2b.web.app"])

def solve_school_timetable(data):
    lessons = data.get("lessons", [])
    timeslots = data.get("timeslots", [])
    rooms = data.get("rooms", ["Default"])

    if not lessons or not timeslots:
        raise ValueError("البيانات ناقصة: يجب توفر الدروس والفترات الزمنية")

    # --- 1. نظام الفحص المسبق (Pre-check) لمنع الفشل غير المبرر ---
    total_available_slots = len(timeslots)
    
    # فحص سعة الفصول
    class_assignments = {}
    for l in lessons:
        class_assignments.setdefault(l['classId'], []).append(l)
    
    for c_id, c_lessons in class_assignments.items():
        if len(c_lessons) > total_available_slots:
            raise Exception(f"خطأ في البيانات: الفصل ({c_id}) لديه {len(c_lessons)} حصة مطلوب توزيعها، ولكن جدولك الأسبوعي لا يحتوي إلا على {total_available_slots} حصة فقط. يرجى زيادة عدد الحصص في الهيكل الزمني.")

    # فحص سعة المعلمين
    teacher_assignments = {}
    for l in lessons:
        teacher_assignments.setdefault(l['teacher'], []).append(l)
    
    for t_name, t_lessons in teacher_assignments.items():
        if len(t_lessons) > total_available_slots:
            raise Exception(f"خطأ في البيانات: المعلم ({t_name}) لديه {len(t_lessons)} حصة، وهذا يتجاوز السعة القصوى للجدول ({total_available_slots} حصة).")

    # --- 2. بناء نموذج OR-Tools ---
    model = cp_model.CpModel()
    assignments = {}

    # إنشاء المتغيرات الثنائية (Boolean Variables)
    for lesson in lessons:
        for t_idx in range(len(timeslots)):
            for r_idx in range(len(rooms)):
                assignments[(lesson["id"], t_idx, r_idx)] = model.NewBoolVar(
                    f'assign_{lesson["id"]}_t{t_idx}_r{r_idx}'
                )

    # القيد الأول: كل درس يجب أن يُسند لحصة واحدة ومكان واحد بالضبط
    for lesson in lessons:
        model.Add(
            sum(assignments[(lesson["id"], t_idx, r_idx)]
                for t_idx in range(len(timeslots))
                for r_idx in range(len(rooms))) == 1
        )

    # القيد الثاني: المعلم لا يمكنه تدريس أكثر من درس في نفس الوقت
    for teacher, t_lessons in teacher_assignments.items():
        for t_idx in range(len(timeslots)):
            model.Add(
                sum(assignments[(lesson["id"], t_idx, r_idx)]
                    for lesson in t_lessons
                    for r_idx in range(len(rooms))) <= 1
            )

    # القيد الثالث: الفصل لا يمكنه أخذ أكثر من درس في نفس الوقت
    for c_id, c_lessons in class_assignments.items():
        for t_idx in range(len(timeslots)):
            model.Add(
                sum(assignments[(lesson["id"], t_idx, r_idx)]
                    for lesson in c_lessons
                    for r_idx in range(len(rooms))) <= 1
            )

    # --- 3. تشغيل المحرك (Solver) ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60.0  # وقت البحث الأقصى
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
                            "timeslot": timeslot 
                        })
        return solution
    else:
        # إذا لم يجد حلاً، نقوم بتحليل السبب
        raise Exception("لا يمكن إيجاد حل يحقق جميع الشروط. قد يكون هناك تضارب في أنصبة المعلمين أو ضيق في عدد الحصص المتاحة لكل فصل.")

# --- 4. إعدادات Flask المسارات ---
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "OK", "message": "Server is running"})

@app.route('/solve', methods=['POST'])
def solve():
    try:
        input_data = request.json
        if not input_data:
            return jsonify({"status": "error", "message": "No data provided"}), 400
            
        result = solve_school_timetable(input_data)
        return jsonify({"status": "success", "timetable": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == '__main__':
    # الحصول على المنفذ من Railway أو استخدام 8000 كافتراضي
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
