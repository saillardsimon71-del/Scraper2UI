import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import Layout from "@/components/Layout";
import FileDuJour from "@/pages/FileDuJour";
import Prospects from "@/pages/Prospects";
import Scraper from "@/pages/Scraper";
import ImportPage from "@/pages/ImportPage";
import Scenarios from "@/pages/Scenarios";
import Parametres from "@/pages/Parametres";

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<FileDuJour />} />
            <Route path="/prospects" element={<Prospects />} />
            <Route path="/scraper" element={<Scraper />} />
            <Route path="/import" element={<ImportPage />} />
            <Route path="/scenarios" element={<Scenarios />} />
            <Route path="/parametres" element={<Parametres />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster position="bottom-right" richColors />
    </div>
  );
}

export default App;
