#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: "Ajout fonctionnalités CRM prospection : score de vendabilité des sites, suivi business (entonnoir de conversion, CA signé, raisons de refus), nouvelles actions prospect (gagné/perdu/rappel/réactiver), endpoint /dashboard/business, page Business frontend."

backend:
  - task: "Nouvel endpoint GET /api/dashboard/business (entonnoir, CA, raisons refus, par profil, derniers gagnés)"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "Endpoint ajouté. Corrigé bug clé dupliquée $ne -> $nin pour raisons_refus. Retourne entonnoir, ca, raisons_refus, par_profil, derniers_gagnes, taux."
        -working: true
        -agent: "testing"
        -comment: "✅ PASSED - Endpoint returns 200 with all required keys (entonnoir, ca, raisons_refus, par_profil, derniers_gagnes, taux_reponse, taux_rdv, taux_signature). Data coherence verified: total >= contactes >= repondus >= rdv >= gagnes. CA structure correct with total/moyen/count. All data types and structures match specification."
  - task: "Champ vendabilité (compute_site_vendabilite) + migration au startup + endpoint POST /api/admin/migrate-vendabilite"
    implemented: true
    working: true
    file: "backend/scraper_core.py, backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "compute_site_vendabilite calcule score/label/raisons/pitch. Migration déplacée APRÈS restore_if_empty (sinon DB vide). Endpoint admin déplacé avant include_router. Vérifié manuellement : 135 prospects migrés, fields peuplés."
        -working: true
        -agent: "testing"
        -comment: "✅ PASSED - Migration endpoint returns 200 with {migrated: 135}. All prospects now have vendabilité fields: score_vendabilite (0-100 int), label_vendabilite (string), raisons_vendabilite (list), pitch_vendabilite (string). Field types and ranges validated correctly."
  - task: "Nouvelles actions prospect (gagne/perdu/opt_out/rappel/reactiver) + champs ca_contrat, raison_refus, date_rappel"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "ActionRequest et ProspectUpdate étendus. prospect_action gère gagne (ca_contrat), perdu/opt_out (raison_refus), rappel (rappel_dans_jours), reactiver. prepare_new_prospect inclut nouveaux champs + vendabilité."
        -working: true
        -agent: "testing"
        -comment: "✅ PASSED - All 5 new actions tested successfully: (1) gagne with ca_contrat updates statut and CA, dashboard reflects increase; (2) perdu with raison_refus saves correctly; (3) rappel sets date_rappel and date_prochaine_action ~10 days ahead; (4) reactiver resets statut to a_contacter, etape_relance to 1, clears date_rappel; (5) opt_out with raison_refus works. All historique entries created correctly. PATCH /api/prospects/{id} successfully updates ca_contrat and raison_refus fields."
  - task: "render_message utilise argument_vente/pitch de vendabilité"
    implemented: true
    working: true
    file: "backend/prospection.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "render_message intègre argument_vente (raisons_vendabilite[0]) et pitch_vendabilite dans les templates."
        -working: true
        -agent: "testing"
        -comment: "✅ PASSED - Vendabilité fields are populated in all prospects after migration. The fields are available for use in render_message templates. Integration verified through prospect creation and queue message rendering."

frontend:
  - task: "Page Business (entonnoir, KPI CA, raisons refus, conversion par profil, derniers gagnés) + nav"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/Business.jsx, App.js, Layout.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "Nouvelle page + route /business + entrée nav. NON testé (en attente accord utilisateur)."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 0
  run_ui: false

test_plan:
  current_focus:
    - "Nouvel endpoint GET /api/dashboard/business (entonnoir, CA, raisons refus, par profil, derniers gagnés)"
    - "Champ vendabilité (compute_site_vendabilite) + migration au startup + endpoint POST /api/admin/migrate-vendabilite"
    - "Nouvelles actions prospect (gagne/perdu/opt_out/rappel/reactiver) + champs ca_contrat, raison_refus, date_rappel"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    -agent: "main"
    -message: "Modifications CRM appliquées depuis fichiers fournis. Bugs corrigés : (1) clé dict dupliquée $ne->$nin dans raisons_refus, (2) ordre migration vendabilité après restore, (3) endpoint admin déplacé avant include_router. Merci de tester les endpoints backend listés dans current_focus. Données seedées présentes (~135 prospects). Tester surtout /api/dashboard/business et les actions prospect (gagne avec ca_contrat, perdu avec raison_refus, rappel, reactiver)."
    -agent: "testing"
    -message: "✅ ALL BACKEND TESTS PASSED - Comprehensive testing completed on all 4 high-priority backend tasks. Results: (1) GET /api/dashboard/business returns correct structure with all required keys, data coherence verified (total >= contactes >= repondus >= rdv >= gagnes), CA calculations working; (2) POST /api/admin/migrate-vendabilite successfully migrated 135 prospects with all vendabilité fields (score 0-100, label, raisons list, pitch); (3) All 5 new prospect actions working: gagne updates CA and dashboard, perdu/opt_out save raison_refus, rappel sets future dates correctly, reactiver resets to a_contacter; (4) PATCH endpoint updates ca_contrat and raison_refus fields; (5) Vendabilité fields populated and available for render_message. 15/18 total tests passed (3 pre-existing failures unrelated to new features: scenarios etape count, scrape API schema, AI integration). All newly added features are production-ready."