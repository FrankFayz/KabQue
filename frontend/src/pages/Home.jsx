import Hero from '../components/home/Hero';
import HomeHowItWorks from '../components/home/HomeHowItWorks';
import HomeCampus from '../components/home/HomeCampus';
import HomeFooter from '../components/home/HomeFooter';

export default function Home() {
  return (
    <div className="home-page">
      <Hero />
      <HomeHowItWorks />
      <HomeCampus />
      <HomeFooter />
    </div>
  );
}
